package host

import (
	"context"
	"encoding/csv"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	execute "github.com/alexellis/go-execute/v2"
	"github.com/dstackai/dstack/runner/internal/log"
)

const amdSmiImage = "un1def/amd-smi:6.2.2-0"

const ttSmiImage = "dstackai/tt-smi:latest"

type GpuVendor string

const (
	GpuVendorNone        GpuVendor = "none"
	GpuVendorNvidia      GpuVendor = "nvidia"
	GpuVendorAmd         GpuVendor = "amd"
	GpuVendorIntel       GpuVendor = "intel"
	GpuVendorTenstorrent GpuVendor = "tenstorrent"
)

type GpuInfo struct {
	Vendor GpuVendor
	Name   string
	Vram   int // MiB
	// NVIDIA: uuid field from nvidia-smi, "globally unique immutable alphanumeric identifier of the GPU",
	// in the form of `GPU-2b79666e-d81f-f3f8-fd47-9903f118c3f5`
	// AMD: empty string (AMD devices have IDs in `amd-smi list`, but we don't need them)
	// Intel: empty string (Gaudi devices have IDs called `uuid`, e.g., `01P0-HL2080A0-15-TNPS14-20-07-07`,
	// but habana Docker runtime only accepts indices, see below)
	ID string
	// NVIDIA: empty string (NVIDIA devices have DRI nodes in udev FS, but we don't need them)
	// AMD: `/dev/dri/renderD<N>` path
	// Intel: empty string
	RenderNodePath string
	// NVIDIA: empty string
	// AMD: empty string
	// Intel: accelerator index: ("0", "1", ...), as reported by `hl-smi -Q index`
	Index string
}

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

func GetGpuInfo(ctx context.Context) []GpuInfo {
	switch gpuVendor := GetGpuVendor(); gpuVendor {
	case GpuVendorNvidia:
		return getNvidiaGpuInfo(ctx)
	case GpuVendorAmd:
		return getAmdGpuInfo(ctx)
	case GpuVendorIntel:
		return getIntelGpuInfo(ctx)
	case GpuVendorTenstorrent:
		return getTenstorrentGpuInfo(ctx)
	case GpuVendorNone:
		return []GpuInfo{}
	}
	return []GpuInfo{}
}

func getNvidiaGpuInfo(ctx context.Context) []GpuInfo {
	gpus := []GpuInfo{}

	cmd := execute.ExecTask{
		Command:     "nvidia-smi",
		Args:        []string{"--query-gpu=name,memory.total,uuid", "--format=csv,noheader,nounits"},
		StreamStdio: false,
	}
	res, err := cmd.Execute(ctx)
	if err != nil {
		log.Error(ctx, "failed to execute nvidia-smi", "err", err)
		return gpus
	}
	if res.ExitCode != 0 {
		log.Error(
			ctx, "failed to execute nvidia-smi",
			"exitcode", res.ExitCode, "stdout", res.Stdout, "stderr", res.Stderr,
		)
		return gpus
	}

	r := csv.NewReader(strings.NewReader(res.Stdout))
	for {
		record, err := r.Read()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			log.Error(ctx, "cannot read csv", "err", err)
			return gpus
		}
		if len(record) != 3 {
			log.Error(ctx, "3 csv fields expected", "len", len(record))
			return gpus
		}
		vram, err := strconv.Atoi(strings.TrimSpace(record[1]))
		if err != nil {
			log.Error(ctx, "invalid VRAM value", "value", record[1])
			vram = 0
		}
		gpus = append(gpus, GpuInfo{
			Vendor: GpuVendorNvidia,
			Name:   strings.TrimSpace(record[0]),
			Vram:   vram,
			ID:     strings.TrimSpace(record[2]),
		})
	}
	return gpus
}

type amdGpu struct {
	Asic amdAsic `json:"asic"`
	Vram amdVram `json:"vram"`
	Bus  amdBus  `json:"bus"`
}

type amdAsic struct {
	Name string `json:"market_name"`
}

type amdVram struct {
	Size amdVramSize `json:"size"`
}

type amdVramSize struct {
	Value int `json:"value"`
}

type amdBus struct {
	BDF string `json:"bdf"` // PCIe Domain:Bus:Device.Function notation
}

func getAmdGpuInfo(ctx context.Context) []GpuInfo {
	gpus := []GpuInfo{}

	cmd := execute.ExecTask{
		Command: "docker",
		Args: []string{
			"run",
			"--rm",
			"--device", "/dev/kfd",
			"--device", "/dev/dri",
			amdSmiImage,
			"static", "--json", "--asic", "--vram", "--bus",
		},
		StreamStdio: false,
	}
	res, err := cmd.Execute(ctx)
	if err != nil {
		log.Error(ctx, "failed to execute amd-smi", "err", err)
		return gpus
	}
	if res.ExitCode != 0 {
		log.Error(
			ctx, "failed to execute amd-smi",
			"exitcode", res.ExitCode, "stdout", res.Stdout, "stderr", res.Stderr,
		)
		return gpus
	}

	var amdGpus []amdGpu
	if err := json.Unmarshal([]byte(res.Stdout), &amdGpus); err != nil {
		log.Error(ctx, "cannot read json", "err", err)
		return gpus
	}
	for _, amdGpu := range amdGpus {
		renderNodePath, err := getAmdRenderNodePath(amdGpu.Bus.BDF)
		if err != nil {
			log.Error(ctx, "failed to resolve render node path", "bdf", amdGpu.Bus.BDF, "err", err)
			continue
		}
		gpus = append(gpus, GpuInfo{
			Vendor:         GpuVendorAmd,
			Name:           amdGpu.Asic.Name,
			Vram:           amdGpu.Vram.Size.Value,
			RenderNodePath: renderNodePath,
		})
	}
	return gpus
}

type ttSmiSnapshot struct {
	DeviceInfo []ttDeviceInfo `json:"device_info"`
}

type ttDeviceInfo struct {
	BoardInfo ttBoardInfo `json:"board_info"`
}

type ttBoardInfo struct {
	BoardType string `json:"board_type"`
	BusID     string `json:"bus_id"`
}

func getTenstorrentGpuInfo(ctx context.Context) []GpuInfo {
	gpus := []GpuInfo{}

	cmd := execute.ExecTask{
		Command: "docker",
		Args: []string{
			"run",
			"--rm",
			"--device", "/dev/tenstorrent",
			ttSmiImage,
			"-s",
		},
		StreamStdio: false,
	}
	res, err := cmd.Execute(ctx)
	if err != nil {
		log.Error(ctx, "failed to execute tt-smi", "err", err)
		return gpus
	}
	if res.ExitCode != 0 {
		log.Error(
			ctx, "failed to execute tt-smi",
			"exitcode", res.ExitCode, "stdout", res.Stdout, "stderr", res.Stderr,
		)
		return gpus
	}

	var ttSmiSnapshot ttSmiSnapshot
	if err := json.Unmarshal([]byte(res.Stdout), &ttSmiSnapshot); err != nil {
		log.Error(ctx, "cannot read tt-smi json", "err", err)
		log.Debug(ctx, "tt-smi output", "stdout", res.Stdout)
		return gpus
	}

	for i, device := range ttSmiSnapshot.DeviceInfo {
		// Extract board type without R/L suffix
		boardType := strings.TrimSpace(device.BoardInfo.BoardType)
		name := boardType

		// Remove " R" or " L" suffix if present
		if strings.HasSuffix(boardType, " R") {
			name = boardType[:len(boardType)-2]
		} else if strings.HasSuffix(boardType, " L") {
			name = boardType[:len(boardType)-2]
		}

		// Determine VRAM based on board type
		vram := 0
		if strings.HasPrefix(name, "n150") {
			vram = 12 * 1024 // 12GB in MiB
		} else if strings.HasPrefix(name, "n300") {
			vram = 24 * 1024 // 24GB in MiB
		}

		gpus = append(gpus, GpuInfo{
			Vendor: GpuVendorTenstorrent,
			Name:   name,
			Vram:   vram,
			ID:     device.BoardInfo.BusID,
			Index:  strconv.Itoa(i),
		})
	}

	return gpus
}

func getAmdRenderNodePath(bdf string) (string, error) {
	// amd-smi uses extended BDF Notation with domain: Domain:Bus:Device.Function, e.g., 0000:5f:00.0
	// udev creates /dev/dri/by-path/pci-<BDF>-render -> ../renderD<N> symlinks
	symlink := fmt.Sprintf("/dev/dri/by-path/pci-%s-render", bdf)
	path, err := filepath.EvalSymlinks(symlink)
	if err != nil {
		return "", err
	}
	return path, nil
}

func IsRenderNodePath(path string) bool {
	return strings.HasPrefix(path, "/dev/dri/renderD")
}

func getIntelGpuInfo(ctx context.Context) []GpuInfo {
	gpus := []GpuInfo{}

	cmd := execute.ExecTask{
		Command:     "hl-smi",
		Args:        []string{"--query-aip=name,memory.total,index", "--format=csv,noheader,nounits"},
		StreamStdio: false,
	}
	res, err := cmd.Execute(ctx)
	if err != nil {
		log.Error(ctx, "failed to execute hl-smi", "err", err)
		return gpus
	}
	if res.ExitCode != 0 {
		log.Error(
			ctx, "failed to execute hl-smi",
			"exitcode", res.ExitCode, "stdout", res.Stdout, "stderr", res.Stderr,
		)
		return gpus
	}

	r := csv.NewReader(strings.NewReader(res.Stdout))
	for {
		record, err := r.Read()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			log.Error(ctx, "cannot read csv", "err", err)
			return gpus
		}
		if len(record) != 3 {
			log.Error(ctx, "3 csv fields expected", "len", len(record))
			return gpus
		}
		vram, err := strconv.Atoi(strings.TrimSpace(record[1]))
		if err != nil {
			log.Error(ctx, "invalid memory value", "value", record[1])
			vram = 0
		}
		gpus = append(gpus, GpuInfo{
			Vendor: GpuVendorIntel,
			Name:   strings.TrimSpace(record[0]),
			Vram:   vram,
			Index:  strings.TrimSpace(record[2]),
		})
	}
	return gpus
}
