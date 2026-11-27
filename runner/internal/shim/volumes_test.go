package shim

import (
	"errors"
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
	"golang.org/x/sys/unix"
)

func TestBindMountedVolume(t *testing.T) {
	source := t.TempDir()
	target := filepath.Join(t.TempDir(), "bind")
	// A provider can leave the directory behind even when its filesystem is missing.
	require.ErrorContains(t, bindMountedVolume(source, target), "not a verified mount point")

	if err := unix.Mount("tmpfs", source, "tmpfs", 0, "size=1m"); errors.Is(err, unix.EPERM) {
		t.Skip("mounting tmpfs requires CAP_SYS_ADMIN")
	} else {
		require.NoError(t, err)
	}
	t.Cleanup(func() { _ = unix.Unmount(source, 0) })
	require.NoError(t, os.WriteFile(filepath.Join(source, "checkpoint"), []byte("saved"), 0o600))
	require.NoError(t, bindMountedVolume(source, target))
	t.Cleanup(func() { _ = unix.Unmount(target, 0) })

	// Removing the provider's original mount must never redirect the job to the local disk.
	require.NoError(t, unix.Unmount(source, 0))
	data, err := os.ReadFile(filepath.Join(target, "checkpoint"))
	require.NoError(t, err)
	require.Equal(t, "saved", string(data))
	require.NoFileExists(t, filepath.Join(source, "checkpoint"))
}
