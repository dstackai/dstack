package netmeter

import (
	"bytes"
	"context"
	"fmt"
	"os/exec"
	"strconv"
	"strings"
	"sync/atomic"
	"time"

	"github.com/dstackai/dstack/runner/internal/common/log"
)

const (
	pollInterval = 10 * time.Second
	chainName    = "dstack-nm"
)

// NetMeter monitors outbound data transfer using iptables byte counters.
// It excludes private/VPC traffic and counts only external (billable) bytes.
// The meter runs for the lifetime of the shim process (per-instance, not per-task).
type NetMeter struct {
	bytes   atomic.Int64
	stopCh  chan struct{}
	stopped chan struct{}
}

// New creates a new NetMeter.
func New() *NetMeter {
	return &NetMeter{
		stopCh:  make(chan struct{}),
		stopped: make(chan struct{}),
	}
}

// Start sets up iptables rules and begins polling byte counters.
func (m *NetMeter) Start(ctx context.Context) error {
	if err := checkIptables(); err != nil {
		return fmt.Errorf("iptables not available: %w", err)
	}

	// Clean up any orphaned chain from a previous shim process
	cleanupChain(ctx)

	if err := setupChain(ctx); err != nil {
		return fmt.Errorf("setup iptables chain: %w", err)
	}

	go m.pollLoop(ctx)
	return nil
}

// Stop signals the poll loop to stop and cleans up iptables rules.
func (m *NetMeter) Stop() {
	close(m.stopCh)
	<-m.stopped
}

// Bytes returns the cumulative external outbound byte count (thread-safe).
func (m *NetMeter) Bytes() int64 {
	return m.bytes.Load()
}

func checkIptables() error {
	_, err := exec.LookPath("iptables")
	return err
}

func setupChain(ctx context.Context) error {
	// Create the chain
	if err := iptables(ctx, "-N", chainName); err != nil {
		return fmt.Errorf("create chain: %w", err)
	}

	// Add exclusion rules for private/internal traffic (these RETURN without counting)
	privateCIDRs := []struct {
		cidr    string
		comment string
	}{
		{"10.0.0.0/8", "VPC/private"},
		{"172.16.0.0/12", "VPC/private"},
		{"192.168.0.0/16", "VPC/private"},
		{"169.254.0.0/16", "link-local/metadata"},
		{"127.0.0.0/8", "loopback"},
	}
	for _, p := range privateCIDRs {
		if err := iptables(ctx, "-A", chainName, "-d", p.cidr, "-j", "RETURN"); err != nil {
			cleanupChain(ctx)
			return fmt.Errorf("add exclusion rule for %s: %w", p.comment, err)
		}
	}

	// Add catch-all counting rule (counts all remaining = external/billable bytes)
	if err := iptables(ctx, "-A", chainName, "-j", "RETURN"); err != nil {
		cleanupChain(ctx)
		return fmt.Errorf("add counting rule: %w", err)
	}

	// Insert jump from OUTPUT chain (catches host-mode Docker and host processes)
	if err := iptables(ctx, "-I", "OUTPUT", "-j", chainName); err != nil {
		cleanupChain(ctx)
		return fmt.Errorf("insert OUTPUT jump: %w", err)
	}

	// Insert jump from FORWARD chain (catches bridge-mode Docker traffic)
	if err := iptables(ctx, "-I", "FORWARD", "-j", chainName); err != nil {
		cleanupChain(ctx)
		return fmt.Errorf("insert FORWARD jump: %w", err)
	}

	return nil
}

func cleanupChain(ctx context.Context) {
	_ = iptables(ctx, "-D", "OUTPUT", "-j", chainName)
	_ = iptables(ctx, "-D", "FORWARD", "-j", chainName)
	_ = iptables(ctx, "-F", chainName)
	_ = iptables(ctx, "-X", chainName)
}

func (m *NetMeter) pollLoop(ctx context.Context) {
	defer close(m.stopped)
	defer cleanupChain(ctx)

	ticker := time.NewTicker(pollInterval)
	defer ticker.Stop()

	for {
		select {
		case <-m.stopCh:
			return
		case <-ticker.C:
			b, err := readCounter(ctx)
			if err != nil {
				log.Error(ctx, "failed to read data transfer counter", "err", err)
				continue
			}
			m.bytes.Store(b)
			log.Debug(ctx, "data transfer meter poll", "bytes", b)
		}
	}
}

// readCounter reads the cumulative byte count from the catch-all rule (last rule in chain).
func readCounter(ctx context.Context) (int64, error) {
	output, err := iptablesOutput(ctx, "-L", chainName, "-v", "-x", "-n")
	if err != nil {
		return 0, err
	}
	return parseByteCounter(output)
}

// parseByteCounter extracts the byte count from the last rule (catch-all counting rule)
// in the iptables -L -v -x -n output.
//
// Example output:
//
//	Chain dstack-nm (1 references)
//	    pkts      bytes target     prot opt in     out     source               destination
//	       0        0 RETURN     all  --  *      *       0.0.0.0/0            10.0.0.0/8
//	       0        0 RETURN     all  --  *      *       0.0.0.0/0            172.16.0.0/12
//	       0        0 RETURN     all  --  *      *       0.0.0.0/0            192.168.0.0/16
//	       0        0 RETURN     all  --  *      *       0.0.0.0/0            169.254.0.0/16
//	       0        0 RETURN     all  --  *      *       0.0.0.0/0            127.0.0.0/8
//	     123  456789 RETURN     all  --  *      *       0.0.0.0/0            0.0.0.0/0
//
// The last rule (destination 0.0.0.0/0) is the catch-all; its bytes field is what we want.
func parseByteCounter(output string) (int64, error) {
	lines := strings.Split(strings.TrimSpace(output), "\n")

	// Find lines that are rule entries (skip header lines)
	var lastRuleLine string
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" {
			continue
		}
		// Skip "Chain ..." and column header lines
		if strings.HasPrefix(trimmed, "Chain ") {
			continue
		}
		if strings.HasPrefix(trimmed, "pkts") {
			continue
		}
		lastRuleLine = trimmed
	}

	if lastRuleLine == "" {
		return 0, fmt.Errorf("no rules found in chain %s", chainName)
	}

	// Parse the bytes field (second field in the line)
	fields := strings.Fields(lastRuleLine)
	if len(fields) < 2 {
		return 0, fmt.Errorf("unexpected rule format: %q", lastRuleLine)
	}

	byteCount, err := strconv.ParseInt(fields[1], 10, 64)
	if err != nil {
		return 0, fmt.Errorf("parse byte count %q: %w", fields[1], err)
	}

	return byteCount, nil
}

func iptables(ctx context.Context, args ...string) error {
	cmd := exec.CommandContext(ctx, "iptables", args...)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("iptables %s: %s: %w", strings.Join(args, " "), stderr.String(), err)
	}
	return nil
}

func iptablesOutput(ctx context.Context, args ...string) (string, error) {
	cmd := exec.CommandContext(ctx, "iptables", args...)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("iptables %s: %s: %w", strings.Join(args, " "), stderr.String(), err)
	}
	return stdout.String(), nil
}
