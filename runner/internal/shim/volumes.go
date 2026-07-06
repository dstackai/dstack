package shim

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"

	"golang.org/x/sys/unix"

	"github.com/dstackai/dstack/runner/internal/common/log"
	"github.com/dstackai/dstack/runner/internal/shim/backends"
)

func prepareVolumes(ctx context.Context, taskConfig TaskConfig) error {
	for _, volume := range taskConfig.Volumes {
		err := formatAndMountVolume(ctx, volume)
		if err != nil {
			return fmt.Errorf("format and mount volume: %w", err)
		}
	}
	return nil
}

func unmountVolumes(ctx context.Context, taskConfig TaskConfig) error {
	if len(taskConfig.Volumes) == 0 {
		return nil
	}
	log.Debug(ctx, "Unmounting volumes...")
	var failed []string
	for _, volume := range taskConfig.Volumes {
		mountPoint := getVolumeMountPoint(volume.Name)
		cmd := exec.CommandContext(ctx, "mountpoint", mountPoint)
		if output, err := cmd.CombinedOutput(); err != nil {
			log.Info(ctx, "skipping", "mountpoint", mountPoint, "output", output)
			continue
		}
		cmd = exec.CommandContext(ctx, "umount", "-qf", mountPoint)
		if output, err := cmd.CombinedOutput(); err != nil {
			log.Error(ctx, "failed to unmount", "mountpoint", mountPoint, "output", output)
			failed = append(failed, mountPoint)
		} else {
			log.Debug(ctx, "unmounted", "mountpoint", mountPoint)
		}
	}
	if len(failed) > 0 {
		return fmt.Errorf("failed to unmount volume(s): %v", failed)
	}
	return nil
}

func formatAndMountVolume(ctx context.Context, volume VolumeInfo) error {
	backend, err := backends.GetBackend(volume.Backend)
	if err != nil {
		return fmt.Errorf("get backend: %w", err)
	}
	deviceName, err := backend.GetRealDeviceName(ctx, volume.VolumeId, volume.DeviceName)
	if err != nil {
		return fmt.Errorf("get real device name: %w", err)
	}
	fsCreated, err := initFileSystem(ctx, deviceName, !volume.InitFs)
	if err != nil {
		return fmt.Errorf("init file system: %w", err)
	}
	// Make FS root directory world-writable (0777) to give any job user
	// a permission to create new files
	// NOTE: mke2fs (that is, mkfs.ext4) supports `-E root_perms=0777` since 1.47.1:
	// https://e2fsprogs.sourceforge.net/e2fsprogs-release.html#1.47.1
	// but, as of 2024-12-04, this version is too new to rely on, for example,
	// Ubuntu 24.04 LTS has only 1.47.0
	// 0 means "do not chmod root directory"
	var fsRootPerms os.FileMode = 0
	// Change permissions only if the FS was created by us, don't mess with
	// user-formatted volumes
	if fsCreated {
		fsRootPerms = 0o777
	}
	err = mountDisk(ctx, deviceName, getVolumeMountPoint(volume.Name), fsRootPerms)
	if err != nil {
		return fmt.Errorf("mount disk: %w", err)
	}
	return nil
}

func getVolumeMountPoint(volumeName string) string {
	// Put volumes in dstack-specific dir to avoid clashes with host dirs.
	// /mnt/disks is used since on some VM images other places may not be writable (e.g. GCP COS).
	return fmt.Sprintf("/mnt/disks/dstack-volumes/%s", volumeName)
}

func prepareInstanceMountPoints(taskConfig TaskConfig) error {
	// If the instance volume directory doesn't exist, create it with world-writable permissions (0777)
	// to give any job user a permission to create new files
	// If the directory already exists, do nothing, don't mess with already set permissions, especially
	// on SSH fleets where permissions are managed by the host admin
	for _, mountPoint := range taskConfig.InstanceMounts {
		if _, err := os.Stat(mountPoint.InstancePath); errors.Is(err, os.ErrNotExist) {
			// All missing parent dirs are created with 0755 permissions
			if err = os.MkdirAll(mountPoint.InstancePath, 0o755); err != nil {
				return fmt.Errorf("create instance mount directory: %w", err)
			}
			if err = os.Chmod(mountPoint.InstancePath, 0o777); err != nil {
				return fmt.Errorf("chmod instance mount directory: %w", err)
			}
		} else if err != nil {
			return fmt.Errorf("stat instance mount directory: %w", err)
		}
	}
	return nil
}

// initFileSystem creates an ext4 file system on a disk only if it does not
// already have one. Returns true if the file system was created.
//
// Safety contract: mkfs is reached ONLY after the device is confirmed to be a
// real, ready, non-zero-sized block device AND a direct superblock probe
// repeatedly confirms no signature.
func initFileSystem(ctx context.Context, deviceName string, errorIfNotExists bool) (bool, error) {
	if err := waitForBlockDevice(ctx, deviceName, 10*time.Second); err != nil {
		return false, fmt.Errorf("device %s not ready: %w", deviceName, err)
	}

	fsType, hasFS, err := hasFilesystem(ctx, deviceName)
	if err != nil {
		return false, fmt.Errorf("failed to check if disk is formatted: %w", err)
	}
	if hasFS {
		log.Debug(ctx, "disk already has a filesystem, skipping format",
			"device", deviceName, "fstype", fsType)
		return false, nil
	}

	if errorIfNotExists {
		return false, fmt.Errorf("disk %s has no file system", deviceName)
	}

	log.Debug(ctx, "formatting disk with ext4 filesystem...", "device", deviceName)
	cmd := exec.CommandContext(ctx, "mkfs.ext4", "-F", deviceName)
	if output, err := cmd.CombinedOutput(); err != nil {
		return false, fmt.Errorf("failed to format disk: %w, output: %s", err, string(output))
	}
	log.Debug(ctx, "disk formatted succesfully!", "device", deviceName)
	return true, nil
}

// waitForBlockDevice blocks until deviceName is a block device with non-zero
// size, or until timeout. The retry loop is for availability (don't fail a job
// on a transient mid-attach state); the non-zero-block-device requirement is
// for safety (don't make a format decision about a not-ready device).
func waitForBlockDevice(ctx context.Context, deviceName string, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	var lastErr error
	for {
		size, err := blockDeviceSize(deviceName)
		if err == nil && size > 0 {
			return nil
		}
		if err != nil {
			lastErr = err
		} else {
			lastErr = fmt.Errorf("device has zero size")
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("not a ready non-zero block device within %s: %w", timeout, lastErr)
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(200 * time.Millisecond):
		}
	}
}

// blockDeviceSize returns the size in bytes of a block device, erroring if the
// path is not a block device or cannot be opened/queried.
func blockDeviceSize(deviceName string) (uint64, error) {
	fi, err := os.Stat(deviceName)
	if err != nil {
		return 0, err
	}
	if fi.Mode()&os.ModeDevice == 0 || fi.Mode()&os.ModeCharDevice != 0 {
		return 0, fmt.Errorf("%s is not a block device", deviceName)
	}
	f, err := os.OpenFile(deviceName, os.O_RDONLY, 0)
	if err != nil {
		return 0, err
	}
	defer func() { _ = f.Close() }()
	// BLKGETSIZE64 returns the device size in bytes.
	size, err := unix.IoctlGetInt(int(f.Fd()), unix.BLKGETSIZE64)
	if err != nil {
		return 0, fmt.Errorf("BLKGETSIZE64 ioctl on %s: %w", deviceName, err)
	}
	return uint64(size), nil
}

// hasFilesystem reports whether deviceName has a filesystem, re-confirming a
// "no filesystem" verdict before believing it.
//
// The check is asymmetric on purpose: it prevents a hypothetical
// transient false "no-fs" from leading to a destructive mkfs.
func hasFilesystem(ctx context.Context, deviceName string) (string, bool, error) {
	const confirmAttempts = 3
	const confirmInterval = 1 * time.Second

	fsType, hasFS, err := probeFilesystem(ctx, deviceName)
	if err != nil || hasFS {
		return fsType, hasFS, err
	}
	for attempt := range confirmAttempts {
		select {
		case <-ctx.Done():
			return "", false, ctx.Err()
		case <-time.After(confirmInterval):
		}
		fsType, hasFS, err = probeFilesystem(ctx, deviceName)
		if err != nil {
			return "", false, err
		}
		if hasFS {
			log.Warning(ctx, "filesystem appeared on re-probe, not formatting",
				"fstype", fsType, "attempt", attempt)
			return fsType, true, nil
		}
	}
	return "", false, nil
}

// probeFilesystem reports the filesystem type on deviceName via a direct
// superblock probe (blkid -p), independent of the udev/lsblk cache.
func probeFilesystem(ctx context.Context, deviceName string) (string, bool, error) {
	cmd := exec.CommandContext(ctx, "blkid", "-p", "-o", "value", "-s", "TYPE", deviceName)
	var out bytes.Buffer
	cmd.Stdout = &out
	runErr := cmd.Run()
	fsType := strings.TrimSpace(out.String())
	if fsType != "" {
		return fsType, true, nil // a filesystem signature was found
	}

	var exitErr *exec.ExitError
	if errors.As(runErr, &exitErr) && exitErr.ExitCode() == 2 {
		return "", false, nil // exit 2: no signature at all -> genuinely blank
	}
	if runErr == nil {
		return "", false, fmt.Errorf(
			"device %s has a non-filesystem signature but no filesystem; likely wrong device resolved",
			deviceName)
	}
	return "", false, fmt.Errorf("blkid probe of %s failed: %w (output: %q)",
		deviceName, runErr, out.String())
}

func mountDisk(ctx context.Context, deviceName, mountPoint string, fsRootPerms os.FileMode) error {
	// Create the mount point directory if it doesn't exist
	if _, err := os.Stat(mountPoint); os.IsNotExist(err) {
		log.Debug(ctx, "creating mount point...", "mountpoint", mountPoint)
		if err := os.MkdirAll(mountPoint, 0o755); err != nil {
			return fmt.Errorf("failed to create mount point: %w", err)
		}
	}

	// Mount the disk to the mount point
	log.Debug(ctx, "mounting disk...", "device", deviceName, "mountpoint", mountPoint)
	cmd := exec.CommandContext(ctx, "mount", deviceName, mountPoint)
	if output, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("failed to mount disk: %w, output: %s", err, string(output))
	}

	if fsRootPerms != 0 {
		if err := os.Chmod(mountPoint, fsRootPerms); err != nil {
			return fmt.Errorf("failed to chmod volume root directory %s: %w", mountPoint, err)
		}
	}

	log.Debug(ctx, "disk mounted successfully!")
	return nil
}
