package common

import (
	"errors"
	"os"
)

type GpuVendor string

const (
	GpuVendorNone        GpuVendor = "none"
	GpuVendorNvidia      GpuVendor = "nvidia"
	GpuVendorAmd         GpuVendor = "amd"
	GpuVendorIntel       GpuVendor = "intel"
	GpuVendorTenstorrent GpuVendor = "tenstorrent"
)

func GetGpuVendor() GpuVendor {
	// FIXME: There might be errors other than os.ErrNotExist that are ignored silently.
	// Propagate and log.
	if _, err := os.Stat("/dev/kfd"); !errors.Is(err, os.ErrNotExist) {
		return GpuVendorAmd
	}
	if _, err := os.Stat("/dev/nvidiactl"); !errors.Is(err, os.ErrNotExist) {
		return GpuVendorNvidia
	}
	if _, err := os.Stat("/dev/accel"); !errors.Is(err, os.ErrNotExist) {
		return GpuVendorIntel
	}
	if _, err := os.Stat("/dev/tenstorrent"); !errors.Is(err, os.ErrNotExist) {
		return GpuVendorTenstorrent
	}
	if _, err := os.Stat("/dev/dxg"); !errors.Is(err, os.ErrNotExist) {
		// WSL2
		if _, err := os.Stat("/usr/lib/wsl/lib/nvidia-smi"); !errors.Is(err, os.ErrNotExist) {
			return GpuVendorNvidia
		}
	}
	return GpuVendorNone
}
