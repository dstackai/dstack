package metrics

import (
	"fmt"
	"os"
	"path"
	"testing"

	"github.com/stretchr/testify/require"
)

const (
	cgroup2MountLine = "cgroup2 /sys/fs/cgroup cgroup2 rw,nosuid,nodev,noexec,relatime,nsdelegate,memory_recursiveprot 0 0"
	cgroupMountLine  = "cgroup /sys/fs/cgroup/cpu,cpuacct cgroup rw,nosuid,nodev,noexec,relatime,cpu,cpuacct 0 0"
	rootMountLine    = "/dev/nvme0n1p5 / ext4 rw,relatime 0 0"
)

func TestGetProcessCgroupMountPoint_ErrorNoCgroupMounts(t *testing.T) {
	procPidMountsPath := createProcFile(t, "mounts", rootMountLine, "malformed line")

	mountPoint, err := getProcessCgroupMountPoint(t.Context(), procPidMountsPath)

	require.ErrorContains(t, err, "no cgroup mounts found")
	require.Equal(t, "", mountPoint)
}

func TestGetProcessCgroupMountPoint_ErrorOnlyCgroupV1Mounts(t *testing.T) {
	procPidMountsPath := createProcFile(t, "mounts", rootMountLine, cgroupMountLine)

	mountPoint, err := getProcessCgroupMountPoint(t.Context(), procPidMountsPath)

	require.ErrorContains(t, err, "only cgroup v1 mounts found")
	require.Equal(t, "", mountPoint)
}

func TestGetProcessCgroupMountPoint_OK(t *testing.T) {
	procPidMountsPath := createProcFile(t, "mounts", rootMountLine, cgroupMountLine, cgroup2MountLine)

	mountPoint, err := getProcessCgroupMountPoint(t.Context(), procPidMountsPath)

	require.NoError(t, err)
	require.Equal(t, "/sys/fs/cgroup", mountPoint)
}

func TestGetProcessCgroupPathname_ErrorNoCgroup(t *testing.T) {
	procPidCgroupPath := createProcFile(t, "cgroup", "malformed entry")

	mountPoint, err := getProcessCgroupPathname(t.Context(), procPidCgroupPath)

	require.ErrorContains(t, err, "no cgroup pathname found")
	require.Equal(t, "", mountPoint)
}

func TestGetProcessCgroupPathname_ErrorOnlyCgroupV1(t *testing.T) {
	procPidCgroupPath := createProcFile(t, "cgroup", "7:cpu,cpuacct:/user.slice")

	pathname, err := getProcessCgroupPathname(t.Context(), procPidCgroupPath)

	require.ErrorContains(t, err, "only cgroup v1 pathnames found")
	require.Equal(t, "", pathname)
}

func TestGetProcessCgroupPathname_OK(t *testing.T) {
	procPidCgroupPath := createProcFile(t, "cgroup", "7:cpu,cpuacct:/user.slice", "0::/user.slice/user-1000.slice/session-1.scope")

	mountPoint, err := getProcessCgroupPathname(t.Context(), procPidCgroupPath)

	require.NoError(t, err)
	require.Equal(t, "/user.slice/user-1000.slice/session-1.scope", mountPoint)
}

func createProcFile(t *testing.T, name string, lines ...string) string {
	t.Helper()
	tmpDir := t.TempDir()
	pth := path.Join(tmpDir, name)
	file, err := os.OpenFile(pth, os.O_WRONLY|os.O_CREATE, 0o600)
	require.NoError(t, err)
	defer func() {
		err := file.Close()
		require.NoError(t, err)
	}()
	for _, line := range lines {
		_, err := fmt.Fprintln(file, line)
		require.NoError(t, err)
	}
	return pth
}
