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

func TestGetMetricsCgroupPath(t *testing.T) {
	for _, tc := range []struct {
		name         string
		processGroup string
		rootMemory   bool
		childMemory  bool
		wantGroup    string
	}{
		{name: "ordinary container", processGroup: "/", rootMemory: true, wantGroup: "/"},
		{name: "dind before nested container", processGroup: "/dind", rootMemory: true, wantGroup: "/"},
		{name: "dind with nested container", processGroup: "/dind", rootMemory: true, childMemory: true, wantGroup: "/"},
		{name: "host cgroup namespace", processGroup: "/system.slice/docker.scope", childMemory: true, wantGroup: "/system.slice/docker.scope"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			mountPoint := t.TempDir()
			procFile := createProcFile(t, "cgroup", "0::"+tc.processGroup)
			if tc.rootMemory {
				require.NoError(t, os.WriteFile(path.Join(mountPoint, "memory.current"), []byte("8192\n"), 0o600))
			}
			if tc.childMemory {
				child := path.Join(mountPoint, tc.processGroup)
				require.NoError(t, os.MkdirAll(child, 0o700))
				require.NoError(t, os.WriteFile(path.Join(child, "memory.current"), []byte("1024\n"), 0o600))
			}
			cgroupPath, err := getMetricsCgroupPath(t.Context(), mountPoint, procFile)
			require.NoError(t, err)
			require.Equal(t, path.Join(mountPoint, tc.wantGroup), cgroupPath)
			collector := &MetricsCollector{}
			memory, err := collector.GetMemoryUsageBytes(cgroupPath)
			require.NoError(t, err)
			if tc.rootMemory {
				require.Equal(t, uint64(8192), memory)
			} else {
				require.Equal(t, uint64(1024), memory)
			}
		})
	}
}

func TestGetMetricsCgroupPath_ErrorMissingProcessCgroup(t *testing.T) {
	_, err := getMetricsCgroupPath(t.Context(), t.TempDir(), path.Join(t.TempDir(), "missing"))
	require.ErrorContains(t, err, "get cgroup pathname")
	require.ErrorIs(t, err, os.ErrNotExist)
}

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
