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
	alias := filepath.Join(t.TempDir(), "mounts")
	require.NoError(t, os.Symlink(filepath.Dir(source), alias))
	require.ErrorIs(t, bindMountedVolume(filepath.Join(alias, filepath.Base(source)), target), unix.ELOOP)
	cfg := TaskConfig{
		ID:           filepath.Base(filepath.Dir(source)),
		Volumes:      []VolumeInfo{{Name: "data", Backend: "massedcompute", MountPath: source}},
		VolumeMounts: []VolumeMountPoint{{Name: "data", Path: "/data"}},
	}
	require.NoError(t, prepareVolumes(t.Context(), cfg))
	t.Cleanup(func() { _ = unmountVolumes(t.Context(), cfg) })
	mounts, err := getVolumeMounts(cfg)
	require.NoError(t, err)
	require.Len(t, mounts, 1)
	require.Equal(t, "/data", mounts[0].Target)
	target = mounts[0].Source

	// Removing the provider's original mount must never redirect the job to the local disk.
	require.NoError(t, unix.Unmount(source, 0))
	data, err := os.ReadFile(filepath.Join(target, "checkpoint"))
	require.NoError(t, err)
	require.Equal(t, "saved", string(data))
	require.NoFileExists(t, filepath.Join(source, "checkpoint"))
	require.NoError(t, unmountVolumes(t.Context(), cfg))
	require.NoDirExists(t, target)
	require.NoError(t, unmountVolumes(t.Context(), cfg))
}

func TestPrepareProviderVolumeWithoutMountPath(t *testing.T) {
	// Older shims ignore mount_path and enter the block-volume path. A missing
	// mount path on a new shim must fail before looking up or formatting devices too.
	cfg := TaskConfig{Volumes: []VolumeInfo{{Backend: "massedcompute", Name: "data"}}}
	require.ErrorContains(t, prepareVolumes(t.Context(), cfg), "unknown backend")
}
