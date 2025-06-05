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
	return GpuVendorNone
}
