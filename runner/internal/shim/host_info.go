package shim

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"

	"github.com/dstackai/dstack/runner/internal/shim/host"
)

type hostInfo struct {
	GpuVendor host.GpuVendor `json:"gpu_vendor"`
	GpuName   string         `json:"gpu_name"`
	GpuMemory int            `json:"gpu_memory"` // MiB
	GpuCount  int            `json:"gpu_count"`
	Addresses []string       `json:"addresses"`
	DiskSize  uint64         `json:"disk_size"` // bytes
	NumCPUs   int            `json:"cpus"`
	Memory    uint64         `json:"memory"` // bytes
}

func WriteHostInfo(dir string, resources Resources) error {
	path := filepath.Join(dir, "host_info.json")
	// if host_info.json already exists, do nothing and return os.ErrExist
	if _, err := os.Stat(path); !errors.Is(err, os.ErrNotExist) {
		return err
	}

	gpuVendor := host.GpuVendorNone
	gpuCount := 0
	gpuMemory := 0
	gpuName := ""
	gpus := resources.Gpus
	if len(gpus) > 0 {
		gpuCount = len(gpus)
		gpuVendor = gpus[0].Vendor
		gpuMemory = gpus[0].Vram
		gpuName = gpus[0].Name
	}
	info := hostInfo{
		GpuVendor: gpuVendor,
		GpuName:   gpuName,
		GpuMemory: gpuMemory,
		GpuCount:  gpuCount,
		Addresses: resources.NetAddresses,
		DiskSize:  resources.DiskSize,
		NumCPUs:   resources.CpuCount,
		Memory:    resources.TotalMemory,
	}

	b, err := json.Marshal(info)
	if err != nil {
		return fmt.Errorf("failed to marshal %s: %w", path, err)
	}

	f, err := os.Create(path)
	if err != nil {
		return fmt.Errorf("failed to create %s: %w", path, err)
	}
	defer f.Close()

	_, err = f.Write(b)
	if err != nil {
		return fmt.Errorf("failed to write %s: %w", path, err)
	}

	err = f.Sync()
	if err != nil {
		return fmt.Errorf("failed to fsync %s: %w", path, err)
	}

	return nil
}
