package metrics

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"

	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/schemas"
)

type MetricsCollector struct {
	cgroupVersion int
}

func NewMetricsCollector() (*MetricsCollector, error) {
	cgroupVersion, err := getCgroupVersion()
	if err != nil {
		return nil, err
	}
	return &MetricsCollector{
		cgroupVersion: cgroupVersion,
	}, nil
}

func (s *MetricsCollector) GetSystemMetrics() (*schemas.SystemMetrics, error) {
	timestamp := time.Now()
	cpuUsage, err := s.GetCPUUsageMicroseconds()
	if err != nil {
		return nil, err
	}
	memoryUsage, err := s.GetMemoryUsageBytes()
	if err != nil {
		return nil, err
	}
	memoryCache, err := s.GetMemoryCacheBytes()
	if err != nil {
		return nil, err
	}
	memoryWorkingSet := memoryUsage - memoryCache
	gpuMetrics, err := s.GetGPUMetrics()
	if err != nil {
		log.Debug(context.TODO(), "Failed to get gpu metrics", "err", err)
	}
	return &schemas.SystemMetrics{
		Timestamp:        timestamp.UnixMicro(),
		CpuUsage:         cpuUsage,
		MemoryUsage:      memoryUsage,
		MemoryWorkingSet: memoryWorkingSet,
		GPUMetrics:       gpuMetrics,
	}, nil
}

func (s *MetricsCollector) GetCPUUsageMicroseconds() (uint64, error) {
	cgroupCPUUsagePath := "/sys/fs/cgroup/cpu.stat"
	if s.cgroupVersion == 1 {
		cgroupCPUUsagePath = "/sys/fs/cgroup/cpuacct/cpuacct.usage"
	}

	data, err := os.ReadFile(cgroupCPUUsagePath)
	if err != nil {
		return 0, fmt.Errorf("could not read CPU usage: %v", err)
	}

	if s.cgroupVersion == 1 {
		// cgroup v1 provides usage in nanoseconds
		usageStr := strings.TrimSpace(string(data))
		cpuUsage, err := strconv.ParseUint(usageStr, 10, 64)
		if err != nil {
			return 0, fmt.Errorf("could not parse CPU usage: %v", err)
		}
		// convert nanoseconds to microseconds
		return cpuUsage / 1000, nil
	}
	// cgroup v2, we need to extract usage_usec from cpu.stat
	lines := strings.Split(string(data), "\n")
	for _, line := range lines {
		if strings.HasPrefix(line, "usage_usec") {
			parts := strings.Fields(line)
			if len(parts) != 2 {
				return 0, fmt.Errorf("unexpected format in cpu.stat")
			}
			usageMicroseconds, err := strconv.ParseUint(parts[1], 10, 64)
			if err != nil {
				return 0, fmt.Errorf("could not parse usage_usec: %v", err)
			}
			return usageMicroseconds, nil
		}
	}
	return 0, fmt.Errorf("usage_usec not found in cpu.stat")
}

func (s *MetricsCollector) GetMemoryUsageBytes() (uint64, error) {
	cgroupMemoryUsagePath := "/sys/fs/cgroup/memory.current"
	if s.cgroupVersion == 1 {
		cgroupMemoryUsagePath = "/sys/fs/cgroup/memory/memory.usage_in_bytes"
	}

	data, err := os.ReadFile(cgroupMemoryUsagePath)
	if err != nil {
		return 0, fmt.Errorf("could not read memory usage: %v", err)
	}
	usageStr := strings.TrimSpace(string(data))

	usedMemory, err := strconv.ParseUint(usageStr, 10, 64)
	if err != nil {
		return 0, fmt.Errorf("could not parse memory usage: %v", err)
	}
	return usedMemory, nil
}

func (s *MetricsCollector) GetMemoryCacheBytes() (uint64, error) {
	cgroupMemoryStatPath := "/sys/fs/cgroup/memory.stat"
	if s.cgroupVersion == 1 {
		cgroupMemoryStatPath = "/sys/fs/cgroup/memory/memory.stat"
	}

	statData, err := os.ReadFile(cgroupMemoryStatPath)
	if err != nil {
		return 0, fmt.Errorf("could not read memory.stat: %v", err)
	}

	lines := strings.Split(string(statData), "\n")
	for _, line := range lines {
		if (s.cgroupVersion == 1 && strings.HasPrefix(line, "total_inactive_file")) ||
			(s.cgroupVersion == 2 && strings.HasPrefix(line, "inactive_file")) {
			parts := strings.Fields(line)
			if len(parts) != 2 {
				return 0, fmt.Errorf("unexpected format in memory.stat")
			}
			cacheBytes, err := strconv.ParseUint(parts[1], 10, 64)
			if err != nil {
				return 0, fmt.Errorf("could not parse cache value: %v", err)
			}
			return cacheBytes, nil
		}
	}
	return 0, fmt.Errorf("inactive_file not found in cpu.stat")
}

func (s *MetricsCollector) GetGPUMetrics() ([]schemas.GPUMetrics, error) {
	metrics := []schemas.GPUMetrics{}

	cmd := exec.Command("nvidia-smi", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits")
	var out bytes.Buffer
	cmd.Stdout = &out
	if err := cmd.Run(); err != nil {
		return metrics, fmt.Errorf("failed to execute nvidia-smi: %v", err)
	}

	lines := strings.Split(strings.TrimSpace(out.String()), "\n")
	for _, line := range lines {
		parts := strings.Split(line, ", ")
		if len(parts) != 2 {
			continue
		}
		memUsed, err := strconv.ParseUint(strings.TrimSpace(parts[0]), 10, 64)
		if err != nil {
			return metrics, fmt.Errorf("failed to parse memory used: %v", err)
		}
		utilization, err := strconv.ParseUint(strings.TrimSpace(strings.TrimSuffix(parts[1], "%")), 10, 64)
		if err != nil {
			return metrics, fmt.Errorf("failed to parse GPU utilization: %v", err)
		}
		metrics = append(metrics, schemas.GPUMetrics{
			GPUMemoryUsage: memUsed * 1024 * 1024, // Convert MiB to bytes
			GPUUtil:        utilization,
		})
	}

	return metrics, nil
}

func getCgroupVersion() (int, error) {
	data, err := os.ReadFile("/proc/self/mountinfo")
	if err != nil {
		return 0, fmt.Errorf("could not read /proc/self/mountinfo: %v", err)
	}

	for _, line := range strings.Split(string(data), "\n") {
		if strings.Contains(line, "cgroup2") {
			return 2, nil
		} else if strings.Contains(line, "cgroup") {
			return 1, nil
		}
	}

	return 0, fmt.Errorf("could not determine cgroup version")
}
