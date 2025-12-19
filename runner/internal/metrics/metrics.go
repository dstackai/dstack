package metrics

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path"
	"strconv"
	"strings"
	"time"

	"github.com/dstackai/dstack/runner/internal/common"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/schemas"
)

type MetricsCollector struct {
	cgroupMountPoint string
	gpuVendor        common.GpuVendor
}

func NewMetricsCollector(ctx context.Context) (*MetricsCollector, error) {
	// It's unlikely that cgroup mount point will change during container lifetime,
	// so we detect it only once and reuse.
	cgroupMountPoint, err := getProcessCgroupMountPoint(ctx, "/proc/self/mounts")
	if err != nil {
		return nil, fmt.Errorf("get cgroup mount point: %w", err)
	}
	gpuVendor := common.GetGpuVendor()
	return &MetricsCollector{
		cgroupMountPoint: cgroupMountPoint,
		gpuVendor:        gpuVendor,
	}, nil
}

func (s *MetricsCollector) GetSystemMetrics(ctx context.Context) (*schemas.SystemMetrics, error) {
	// It's possible to move a process from one control group to another (it's unlikely, but nonetheless),
	// so we detect the current group each time.
	cgroupPathname, err := getProcessCgroupPathname(ctx, "/proc/self/cgroup")
	if err != nil {
		return nil, fmt.Errorf("get cgroup pathname: %w", err)
	}
	cgroupPath := path.Join(s.cgroupMountPoint, cgroupPathname)
	timestamp := time.Now()
	cpuUsage, err := s.GetCPUUsageMicroseconds(cgroupPath)
	if err != nil {
		return nil, err
	}
	memoryUsage, err := s.GetMemoryUsageBytes(cgroupPath)
	if err != nil {
		return nil, err
	}
	memoryCache, err := s.GetMemoryCacheBytes(cgroupPath)
	if err != nil {
		return nil, err
	}
	memoryWorkingSet := memoryUsage - memoryCache
	gpuMetrics, err := s.GetGPUMetrics(ctx)
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

func (s *MetricsCollector) GetCPUUsageMicroseconds(cgroupPath string) (uint64, error) {
	cgroupCPUUsagePath := path.Join(cgroupPath, "cpu.stat")

	data, err := os.ReadFile(cgroupCPUUsagePath)
	if err != nil {
		return 0, fmt.Errorf("could not read CPU usage: %w", err)
	}

	lines := strings.Split(string(data), "\n")
	for _, line := range lines {
		if strings.HasPrefix(line, "usage_usec") {
			parts := strings.Fields(line)
			if len(parts) != 2 {
				return 0, fmt.Errorf("unexpected format in cpu.stat")
			}
			usageMicroseconds, err := strconv.ParseUint(parts[1], 10, 64)
			if err != nil {
				return 0, fmt.Errorf("could not parse usage_usec: %w", err)
			}
			return usageMicroseconds, nil
		}
	}
	return 0, fmt.Errorf("usage_usec not found in cpu.stat")
}

func (s *MetricsCollector) GetMemoryUsageBytes(cgroupPath string) (uint64, error) {
	cgroupMemoryUsagePath := path.Join(cgroupPath, "memory.current")

	data, err := os.ReadFile(cgroupMemoryUsagePath)
	if err != nil {
		return 0, fmt.Errorf("could not read memory usage: %w", err)
	}
	usageStr := strings.TrimSpace(string(data))

	usedMemory, err := strconv.ParseUint(usageStr, 10, 64)
	if err != nil {
		return 0, fmt.Errorf("could not parse memory usage: %w", err)
	}
	return usedMemory, nil
}

func (s *MetricsCollector) GetMemoryCacheBytes(cgroupPath string) (uint64, error) {
	cgroupMemoryStatPath := path.Join(cgroupPath, "memory.stat")

	statData, err := os.ReadFile(cgroupMemoryStatPath)
	if err != nil {
		return 0, fmt.Errorf("could not read memory.stat: %w", err)
	}

	lines := strings.Split(string(statData), "\n")
	for _, line := range lines {
		if strings.HasPrefix(line, "inactive_file") {
			parts := strings.Fields(line)
			if len(parts) != 2 {
				return 0, fmt.Errorf("unexpected format in memory.stat")
			}
			cacheBytes, err := strconv.ParseUint(parts[1], 10, 64)
			if err != nil {
				return 0, fmt.Errorf("could not parse cache value: %w", err)
			}
			return cacheBytes, nil
		}
	}
	return 0, fmt.Errorf("inactive_file not found in cpu.stat")
}

func (s *MetricsCollector) GetGPUMetrics(ctx context.Context) ([]schemas.GPUMetrics, error) {
	var metrics []schemas.GPUMetrics
	var err error
	switch s.gpuVendor {
	case common.GpuVendorNvidia:
		metrics, err = s.GetNVIDIAGPUMetrics(ctx)
	case common.GpuVendorAmd:
		metrics, err = s.GetAMDGPUMetrics(ctx)
	case common.GpuVendorIntel:
		metrics, err = s.GetIntelAcceleratorMetrics(ctx)
	case common.GpuVendorTenstorrent:
		err = errors.New("tenstorrent metrics not suppored")
	case common.GpuVendorNone:
		// pass
	}
	if metrics == nil {
		metrics = []schemas.GPUMetrics{}
	}
	return metrics, err
}

func (s *MetricsCollector) GetNVIDIAGPUMetrics(ctx context.Context) ([]schemas.GPUMetrics, error) {
	cmd := exec.CommandContext(ctx, "nvidia-smi", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits")
	var out bytes.Buffer
	cmd.Stdout = &out
	if err := cmd.Run(); err != nil {
		return []schemas.GPUMetrics{}, fmt.Errorf("failed to execute nvidia-smi: %w", err)
	}
	return parseNVIDIASMILikeMetrics(out.String())
}

func (s *MetricsCollector) GetAMDGPUMetrics(ctx context.Context) ([]schemas.GPUMetrics, error) {
	cmd := exec.CommandContext(ctx, "amd-smi", "monitor", "-vu", "--csv")
	var out bytes.Buffer
	cmd.Stdout = &out
	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("failed to execute amd-smi: %w", err)
	}
	return s.getAMDGPUMetrics(out.String())
}

func (s *MetricsCollector) getAMDGPUMetrics(csv string) ([]schemas.GPUMetrics, error) {
	lines := strings.Split(strings.TrimSpace(csv), "\n")
	if len(lines) < 2 {
		return nil, errors.New("too few lines in amd-smi output")
	}

	gpuUtilIndex := -1
	memUsedIndex := -1
	for index, header := range strings.Split(lines[0], ",") {
		switch header {
		case "gfx":
			gpuUtilIndex = index
		case "vram_used":
			memUsedIndex = index
		}
	}
	if gpuUtilIndex == -1 {
		return nil, errors.New("GPU utilization column not found")
	}
	if memUsedIndex == -1 {
		return nil, errors.New("used VRAM column not found")
	}

	metrics := []schemas.GPUMetrics{}
	for _, line := range lines[1:] {
		fields := strings.Split(line, ",")
		if len(fields) <= gpuUtilIndex || len(fields) <= memUsedIndex {
			return nil, errors.New("too few columns in amd-smi output")
		}

		gpuUtilRaw := strings.TrimSpace(fields[gpuUtilIndex])
		if strings.ToUpper(gpuUtilRaw) == "N/A" {
			return nil, errors.New("GPU utilization is N/A")
		}
		gpuUtil, err := strconv.ParseUint(gpuUtilRaw, 10, 64)
		if err != nil {
			return nil, fmt.Errorf("failed to parse GPU utilization: %w", err)
		}

		memUsedRaw := strings.TrimSpace(fields[memUsedIndex])
		if strings.ToUpper(memUsedRaw) == "N/A" {
			return nil, errors.New("used VRAM is N/A")
		}
		memUsed, err := strconv.ParseUint(memUsedRaw, 10, 64)
		if err != nil {
			return nil, fmt.Errorf("failed to parse used VRAM: %w", err)
		}
		metrics = append(metrics, schemas.GPUMetrics{
			GPUMemoryUsage: memUsed * 1024 * 1024,
			GPUUtil:        gpuUtil,
		})
	}

	return metrics, nil
}

func (s *MetricsCollector) GetIntelAcceleratorMetrics(ctx context.Context) ([]schemas.GPUMetrics, error) {
	cmd := exec.CommandContext(ctx, "hl-smi", "--query-aip=memory.used,utilization.aip", "--format=csv,noheader,nounits")
	var out bytes.Buffer
	cmd.Stdout = &out
	if err := cmd.Run(); err != nil {
		return []schemas.GPUMetrics{}, fmt.Errorf("failed to execute hl-smi: %w", err)
	}
	return parseNVIDIASMILikeMetrics(out.String())
}

func parseNVIDIASMILikeMetrics(output string) ([]schemas.GPUMetrics, error) {
	metrics := []schemas.GPUMetrics{}

	lines := strings.Split(strings.TrimSpace(output), "\n")
	for _, line := range lines {
		parts := strings.Split(line, ", ")
		if len(parts) != 2 {
			continue
		}
		memUsed, err := strconv.ParseUint(strings.TrimSpace(parts[0]), 10, 64)
		if err != nil {
			return metrics, fmt.Errorf("failed to parse memory used: %w", err)
		}
		utilization, err := strconv.ParseUint(strings.TrimSpace(strings.TrimSuffix(parts[1], "%")), 10, 64)
		if err != nil {
			return metrics, fmt.Errorf("failed to parse accelerator utilization: %w", err)
		}
		metrics = append(metrics, schemas.GPUMetrics{
			GPUMemoryUsage: memUsed * 1024 * 1024, // Convert MiB to bytes
			GPUUtil:        utilization,
		})
	}

	return metrics, nil
}
