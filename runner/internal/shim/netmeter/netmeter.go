package netmeter

import (
	"bytes"
	"context"
	"fmt"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/dstackai/dstack/runner/internal/common/log"
)

const (
	pollInterval = 10 * time.Second
	chainPrefix  = "dstack-nm-"
)

// NetMeter monitors outbound data transfer using iptables byte counters.
// It excludes private/VPC traffic and counts only external (billable) bytes.
// When cumulative bytes exceed the configured quota, the Exceeded() channel is closed.
type NetMeter struct {
	quota     int64  // total bytes for job lifetime
	chainName string // unique iptables chain name

	exceeded     chan struct{}
	exceededOnce sync.Once
	stopCh       chan struct{}
	stopped      chan struct{}
}

// New creates a new NetMeter with the given quota in bytes.
func New(taskID string, quota int64) *NetMeter {
	// Use first 8 chars of task ID for chain name uniqueness
	suffix := taskID
	if len(suffix) > 8 {
		suffix = suffix[:8]
	}
	return &NetMeter{
		quota:     quota,
		chainName: chainPrefix + suffix,
		exceeded:  make(chan struct{}),
		stopCh:    make(chan struct{}),
		stopped:   make(chan struct{}),
	}
}

// Start sets up iptables rules and begins polling byte counters.
func (m *NetMeter) Start(ctx context.Context) error {
	if err := checkIptables(); err != nil {
		return fmt.Errorf("iptables not available: %w", err)
	}

	if err := m.setupChain(ctx); err != nil {
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

// Exceeded returns a channel that is closed when the quota is exceeded.
func (m *NetMeter) Exceeded() <-chan struct{} {
	return m.exceeded
}

func checkIptables() error {
	_, err := exec.LookPath("iptables")
	return err
}

func (m *NetMeter) setupChain(ctx context.Context) error {
	// Create the chain
	if err := iptables(ctx, "-N", m.chainName); err != nil {
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
		if err := iptables(ctx, "-A", m.chainName, "-d", p.cidr, "-j", "RETURN"); err != nil {
			m.cleanup(ctx)
			return fmt.Errorf("add exclusion rule for %s: %w", p.comment, err)
		}
	}

	// Add catch-all counting rule (counts all remaining = external/billable bytes)
	if err := iptables(ctx, "-A", m.chainName, "-j", "RETURN"); err != nil {
		m.cleanup(ctx)
		return fmt.Errorf("add counting rule: %w", err)
	}

	// Insert jump from OUTPUT chain (catches host-mode Docker and host processes)
	if err := iptables(ctx, "-I", "OUTPUT", "-j", m.chainName); err != nil {
		m.cleanup(ctx)
		return fmt.Errorf("insert OUTPUT jump: %w", err)
	}

	// Insert jump from FORWARD chain (catches bridge-mode Docker traffic)
	if err := iptables(ctx, "-I", "FORWARD", "-j", m.chainName); err != nil {
		m.cleanup(ctx)
		return fmt.Errorf("insert FORWARD jump: %w", err)
	}

	return nil
}

func (m *NetMeter) cleanup(ctx context.Context) {
	// Remove jumps from OUTPUT and FORWARD (ignore errors — may not exist if setup failed partway)
	_ = iptables(ctx, "-D", "OUTPUT", "-j", m.chainName)
	_ = iptables(ctx, "-D", "FORWARD", "-j", m.chainName)
	// Flush and delete chain
	_ = iptables(ctx, "-F", m.chainName)
	_ = iptables(ctx, "-X", m.chainName)
}

func (m *NetMeter) pollLoop(ctx context.Context) {
	defer close(m.stopped)
	defer m.cleanup(ctx)

	ticker := time.NewTicker(pollInterval)
	defer ticker.Stop()

	for {
		select {
		case <-m.stopCh:
			return
		case <-ticker.C:
			bytes, err := m.readCounter(ctx)
			if err != nil {
				log.Error(ctx, "failed to read network counter", "chain", m.chainName, "err", err)
				continue
			}
			if bytes > m.quota {
				log.Error(ctx, "data transfer quota exceeded",
					"chain", m.chainName, "bytes", bytes, "quota", m.quota)
				m.exceededOnce.Do(func() { close(m.exceeded) })
				return
			}
		}
	}
}

// readCounter reads the cumulative byte count from the catch-all rule (last rule in chain).
func (m *NetMeter) readCounter(ctx context.Context) (int64, error) {
	output, err := iptablesOutput(ctx, "-L", m.chainName, "-v", "-x", "-n")
	if err != nil {
		return 0, err
	}
	return parseByteCounter(output, m.chainName)
}

// parseByteCounter extracts the byte count from the last rule (catch-all counting rule)
// in the iptables -L -v -x -n output.
//
// Example output:
//
//	Chain dstack-nm-abcd1234 (1 references)
//	    pkts      bytes target     prot opt in     out     source               destination
//	       0        0 RETURN     all  --  *      *       0.0.0.0/0            10.0.0.0/8
//	       0        0 RETURN     all  --  *      *       0.0.0.0/0            172.16.0.0/12
//	       0        0 RETURN     all  --  *      *       0.0.0.0/0            192.168.0.0/16
//	       0        0 RETURN     all  --  *      *       0.0.0.0/0            169.254.0.0/16
//	       0        0 RETURN     all  --  *      *       0.0.0.0/0            127.0.0.0/8
//	     123  456789 RETURN     all  --  *      *       0.0.0.0/0            0.0.0.0/0
//
// The last rule (destination 0.0.0.0/0) is the catch-all; its bytes field is what we want.
func parseByteCounter(output string, chainName string) (int64, error) {
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

// CleanupOrphanedChains removes any leftover dstack-nm-* chains from previous runs.
// Call this on shim startup.
func CleanupOrphanedChains(ctx context.Context) {
	output, err := iptablesOutput(ctx, "-L", "-n")
	if err != nil {
		return
	}
	for _, line := range strings.Split(output, "\n") {
		if strings.HasPrefix(line, "Chain "+chainPrefix) {
			fields := strings.Fields(line)
			if len(fields) >= 2 {
				chainName := fields[1]
				log.Info(ctx, "cleaning up orphaned data transfer meter chain", "chain", chainName)
				_ = iptables(ctx, "-D", "OUTPUT", "-j", chainName)
				_ = iptables(ctx, "-D", "FORWARD", "-j", chainName)
				_ = iptables(ctx, "-F", chainName)
				_ = iptables(ctx, "-X", chainName)
			}
		}
	}
}
