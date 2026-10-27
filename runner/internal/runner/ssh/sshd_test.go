package ssh

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
	"golang.org/x/sys/unix"
)

func TestSshdStartIgnoresCallerCancellation(t *testing.T) {
	readyPath := filepath.Join(t.TempDir(), "ready")
	require.NoError(t, unix.Mkfifo(readyPath, 0o600))
	// Exits with 0 on SIGTERM, as sshd does. Writing to the FIFO blocks until the test reads
	// it, so the test cannot stop the script before the trap is installed.
	d := newFakeSshd(t, fmt.Sprintf("trap 'kill $!; exit 0' TERM; sleep 60 & echo > %s; wait", readyPath))
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	// exec.CommandContext refuses to start on a context that is already done, so Start
	// only succeeds if sshd's lifetime is detached from the caller's context
	require.NoError(t, d.Start(ctx))
	_, err := os.ReadFile(readyPath)
	require.NoError(t, err)
	require.NoError(t, d.Stop(context.Background()))
}

func TestSshdStopReportsFailure(t *testing.T) {
	d := newFakeSshd(t, "exit 1")
	require.NoError(t, d.Start(context.Background()))

	var exitErr *exec.ExitError
	require.ErrorAs(t, d.Stop(context.Background()), &exitErr)
}

// newFakeSshd returns an Sshd that runs script in place of the sshd binary. Spawning a shell
// costs a few milliseconds, and it is what exercises the real os/exec cancellation.
func newFakeSshd(t *testing.T, script string) *Sshd {
	t.Helper()
	binPath := filepath.Join(t.TempDir(), "sshd")
	require.NoError(t, os.WriteFile(binPath, []byte("#!/bin/sh\n"+script+"\n"), 0o755))
	return &Sshd{binPath: binPath, confPath: "sshd_config", logPath: "sshd.log"}
}
