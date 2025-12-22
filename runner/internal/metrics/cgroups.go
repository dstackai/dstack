package metrics

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"os"
	"strings"

	"github.com/dstackai/dstack/runner/internal/log"
)

func getProcessCgroupMountPoint(ctx context.Context, ProcPidMountsPath string) (string, error) {
	// See proc_pid_mounts(5) for the ProcPidMountsPath file description
	file, err := os.Open(ProcPidMountsPath)
	if err != nil {
		return "", fmt.Errorf("open mounts file: %w", err)
	}
	defer func() {
		_ = file.Close()
	}()

	mountPoint := ""
	hasCgroupV1 := false

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := scanner.Text()
		// See fstab(5) for the format description
		fields := strings.Fields(line)
		if len(fields) != 6 {
			log.Warning(ctx, "Unexpected number of fields in mounts file", "num", len(fields), "line", line)
			continue
		}
		fsType := fields[2]
		if fsType == "cgroup2" {
			mountPoint = fields[1]
			break
		}
		if fsType == "cgroup" {
			hasCgroupV1 = true
		}
	}
	if err := scanner.Err(); err != nil {
		log.Warning(ctx, "Error while scanning mounts file", "err", err)
	}

	if mountPoint != "" {
		return mountPoint, nil
	}

	if hasCgroupV1 {
		return "", errors.New("only cgroup v1 mounts found")
	}

	return "", errors.New("no cgroup mounts found")
}

func getProcessCgroupPathname(ctx context.Context, procPidCgroupPath string) (string, error) {
	// See cgroups(7) for the procPidCgroupPath file description
	file, err := os.Open(procPidCgroupPath)
	if err != nil {
		return "", fmt.Errorf("open cgroup file: %w", err)
	}
	defer func() {
		_ = file.Close()
	}()

	pathname := ""
	hasCgroupV1 := false

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := scanner.Text()
		// See cgroups(7) for the format description
		fields := strings.Split(line, ":")
		if len(fields) != 3 {
			log.Warning(ctx, "Unexpected number of fields in cgroup file", "num", len(fields), "line", line)
			continue
		}
		if fields[0] != "0" {
			hasCgroupV1 = true
			continue
		}
		if fields[1] != "" {
			// Must be empty for v2
			log.Warning(ctx, "Unexpected v2 entry in cgroup file", "num", "line", line)
			continue
		}
		pathname = fields[2]
		break
	}
	if err := scanner.Err(); err != nil {
		log.Warning(ctx, "Error while scanning cgroup file", "err", err)
	}

	if pathname != "" {
		return pathname, nil
	}

	if hasCgroupV1 {
		return "", errors.New("only cgroup v1 pathnames found")
	}

	return "", errors.New("no cgroup pathname found")
}
