package gpu

import (
	"context"
	"errors"
	"os"

	"github.com/dstackai/dstack/runner/internal/common/log"
)

type GpuVendor string

const (
	GpuVendorNone        GpuVendor = "none"
	GpuVendorNvidia      GpuVendor = "nvidia"
	GpuVendorAmd         GpuVendor = "amd"
	GpuVendorIntel       GpuVendor = "intel"
	GpuVendorTenstorrent GpuVendor = "tenstorrent"
)

func GetGpuVendor(ctx context.Context) GpuVendor {
	// Some devices can be detected unambiguously -- they have unique device paths.
	//
	// The order within this group does not matter -- false positives are unlikely,
	// but more likely options should be checked first (e.g., NVIDIA before Tenstorrent).
	//
	// This group **must** stay before the ambiguous one below, otherwise a host with
	// an AMD iGPU and an NVIDIA dGPU (a common combination) is detected as AMD,
	// see: https://github.com/dstackai/dstack/issues/4085

	// NVIDIA
	if checkPath(ctx, "/dev/nvidiactl") {
		return GpuVendorNvidia
	}
	// NVIDIA on WSL2
	if checkPath(ctx, "/dev/dxg") && checkPath(ctx, "/usr/lib/wsl/lib/nvidia-smi") {
		return GpuVendorNvidia
	}
	// Tenstorrent
	if checkPath(ctx, "/dev/tenstorrent") {
		return GpuVendorTenstorrent
	}

	// The following devices are tricky -- the same paths are used for devices that we
	// support and expect and devices that we don't support and don't want to support, such
	// as AMD iGPUs or AMD/Intel NPUs integrated into CPUs.
	//
	// The order **does** matter, since both paths can be present on the same host, e.g., an
	// AMD dGPU (/dev/kfd) on a host with an AMD NPU (/dev/accel). We decided to check for AMD
	// first and Intel Gaudi last, because /dev/kfd is the more reliable signal of the two:
	// * /dev/kfd is at least vendor-specific -- it identifies the vendor but not the device class
	// * /dev/accel is standardized[1] vendor-agnostic path used by (including but not limited to):
	//   Intel (Habana Labs devices and NPU), AMD, Qualcomm, Rockchip -- it identifies neither,
	//   so mapping it to Intel Gaudi is a last-resort guess
	//
	// Apparently, there are also far more legit AMD accelerators (e.g., Instinct) deployed in
	// the wild than Intel Gaudi accelerators, so the guess we make more often is the better one.
	//
	// [1]: https://github.com/torvalds/linux/blob/master/Documentation/accel/introduction.rst

	// AMD, **including** iGPU
	if checkPath(ctx, "/dev/kfd") {
		return GpuVendorAmd
	}
	// Intel/Habana Labs Gaudi OR some other compute accelerator
	if checkPath(ctx, "/dev/accel") {
		return GpuVendorIntel
	}

	return GpuVendorNone
}

func checkPath(ctx context.Context, path string) bool {
	_, err := os.Stat(path)
	if err == nil {
		return true
	}
	if !errors.Is(err, os.ErrNotExist) {
		log.Error(ctx, "Failed to check path while detecting accelerator", "path", path, "err", err)
	}
	return false
}
