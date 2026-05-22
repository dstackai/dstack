package host

import (
	"context"
	"encoding/csv"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	execute "github.com/alexellis/go-execute/v2"

	"github.com/dstackai/dstack/runner/internal/common/gpu"
	"github.com/dstackai/dstack/runner/internal/common/log"
)

const (
	amdSmiImage = "dstackai/amd-smi:latest"
	ttSmiImage  = "dstackai/tt-smi:latest"
)

type GpuInfo struct {
	Vendor gpu.GpuVendor
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

func GetGpuInfo(ctx context.Context) []GpuInfo {
	switch gpuVendor := gpu.GetGpuVendor(); gpuVendor {
	case gpu.GpuVendorNvidia:
		return getNvidiaGpuInfo(ctx)
	case gpu.GpuVendorAmd:
		return getAmdGpuInfo(ctx)
	case gpu.GpuVendorIntel:
		return getIntelGpuInfo(ctx)
	case gpu.GpuVendorTenstorrent:
		return getTenstorrentGpuInfo(ctx)
	case gpu.GpuVendorNone:
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
			Vendor: gpu.GpuVendorNvidia,
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

// amd-smi >= 7.x wraps the array in {"gpu_data": [...]}
type amdSmiOutput struct {
	GpuData []amdGpu `json:"gpu_data"`
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

// parseAmdSmiOutput handles both amd-smi output formats:
// ROCm 6.x returns a flat array: [{"gpu": 0, ...}, ...]
// ROCm 7.x wraps it: {"gpu_data": [{"gpu": 0, ...}, ...]}
func parseAmdSmiOutput(data []byte) ([]amdGpu, error) {
	var amdGpus []amdGpu
	if err := json.Unmarshal(data, &amdGpus); err == nil {
		return amdGpus, nil
	}
	var wrapped amdSmiOutput
	if err := json.Unmarshal(data, &wrapped); err != nil {
		return nil, err
	}
	return wrapped.GpuData, nil
}

func getAmdGpuInfo(ctx context.Context) []GpuInfo {
	gpus := []GpuInfo{}

	ctx, cancel := context.WithTimeout(ctx, 2*time.Minute)
	defer cancel()

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

	amdGpus, err := parseAmdSmiOutput([]byte(res.Stdout))
	if err != nil {
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
			Vendor:         gpu.GpuVendorAmd,
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
	BoardID   string `json:"board_id"`
	BusID     string `json:"bus_id"`
}

func unmarshalTtSmiSnapshot(data []byte) (*ttSmiSnapshot, error) {
	var snapshot ttSmiSnapshot
	if err := json.Unmarshal(data, &snapshot); err != nil {
		return nil, err
	}
	return &snapshot, nil
}

func normalizeTtBoardName(name string) string {
	switch {
	case name == "bh-scrappy" || name == "p100":
		return "p100a"
	case strings.HasPrefix(name, "p150"):
		return "p150"
	case strings.HasPrefix(name, "p300"):
		return "p300"
	default:
		return name
	}
}

func splitTtBoardType(boardType string) (name string, suffix string) {
	boardType = strings.TrimSpace(boardType)
	if strings.HasSuffix(boardType, " L") || strings.HasSuffix(boardType, " R") {
		suffix = boardType[len(boardType)-1:]
		boardType = strings.TrimSpace(boardType[:len(boardType)-2])
	}
	return normalizeTtBoardName(boardType), suffix
}

func ttBoardVramMib(name string) int {
	switch name {
	case "n150", "n300", "tt-galaxy-wh":
		return 12 * 1024
	case "p100a":
		return 28 * 1024
	case "p150", "p300", "tt-galaxy-bh":
		return 32 * 1024
	default:
		return 0
	}
}

func isTtBlackholeBoard(name string) bool {
	switch name {
	case "p100a", "p150", "p300", "tt-galaxy-bh":
		return true
	default:
		return false
	}
}

func isRemoteTtDevice(device ttDeviceInfo) bool {
	return strings.EqualFold(strings.TrimSpace(device.BoardInfo.BusID), "N/A")
}

func getGpusFromTtSmiSnapshot(snapshot *ttSmiSnapshot) []GpuInfo {
	gpuMap := make(map[string]*GpuInfo)
	gpuKeys := []string{}
	indexCounter := 0
	addGpu := func(key string, gpuInfo GpuInfo) {
		gpuMap[key] = &gpuInfo
		gpuKeys = append(gpuKeys, key)
	}

	// First pass: identify all "L" and "R" devices
	for i, device := range snapshot.DeviceInfo {
		boardID := device.BoardInfo.BoardID
		name, suffix := splitTtBoardType(device.BoardInfo.BoardType)

		if suffix == "L" {
			// Create unique identifier for this "L" device
			uniqueID := fmt.Sprintf("%s_L_%d", boardID, i)

			// Determine base VRAM based on board type
			baseVram := ttBoardVramMib(name)

			// Create new GPU entry for "L" device
			addGpu(uniqueID, GpuInfo{
				Vendor: gpu.GpuVendorTenstorrent,
				Name:   name,
				Vram:   baseVram,
				ID:     boardID,
				Index:  strconv.Itoa(indexCounter),
			})
			indexCounter++
		}
	}

	// Second pass: add memory from "R" devices to corresponding "L" devices
	for _, device := range snapshot.DeviceInfo {
		boardID := device.BoardInfo.BoardID
		name, suffix := splitTtBoardType(device.BoardInfo.BoardType)

		if suffix == "R" {
			// Find the corresponding "L" device with the same board_id
			// Since we need to match "R" to "L", we'll use the board_id as the key
			// and add memory to the first "L" device we find with that board_id
			for _, key := range gpuKeys {
				gpu := gpuMap[key]
				if gpu.ID == boardID && gpu.Name == name {
					// Add memory to the "L" device
					gpu.Vram += ttBoardVramMib(name)
					break // Only add to the first matching "L" device
				}
			}
		}
	}

	// Handle devices without L/R suffix (backward compatibility)
	for i, device := range snapshot.DeviceInfo {
		boardID := device.BoardInfo.BoardID
		name, suffix := splitTtBoardType(device.BoardInfo.BoardType)

		if suffix == "" {
			// For devices without L/R suffix, treat them as standalone GPUs
			// This maintains backward compatibility with existing data
			uniqueID := fmt.Sprintf("%s_standalone_%d", boardID, i)

			// Determine base VRAM based on board type
			baseVram := ttBoardVramMib(name)

			if isTtBlackholeBoard(name) {
				if isRemoteTtDevice(device) {
					continue
				}
				addGpu(uniqueID, GpuInfo{
					Vendor: gpu.GpuVendorTenstorrent,
					Name:   name,
					Vram:   baseVram,
					ID:     boardID,
					Index:  strconv.Itoa(indexCounter),
				})
				indexCounter++
				continue
			}

			// Check if we already have a GPU with this board_id (old behavior)
			existingGpu := false
			for _, key := range gpuKeys {
				gpu := gpuMap[key]
				if gpu.ID == boardID && gpu.Name == name {
					gpu.Vram += baseVram
					existingGpu = true
					break
				}
			}

			if !existingGpu {
				// Create new GPU entry
				addGpu(uniqueID, GpuInfo{
					Vendor: gpu.GpuVendorTenstorrent,
					Name:   name,
					Vram:   baseVram,
					ID:     boardID,
					Index:  strconv.Itoa(indexCounter),
				})
				indexCounter++
			}
		}
	}

	// Add memory from remote Blackhole chips to the matching local board.
	for _, device := range snapshot.DeviceInfo {
		boardID := device.BoardInfo.BoardID
		name, suffix := splitTtBoardType(device.BoardInfo.BoardType)
		if suffix != "" || !isTtBlackholeBoard(name) || !isRemoteTtDevice(device) {
			continue
		}
		for _, key := range gpuKeys {
			gpu := gpuMap[key]
			if gpu.ID == boardID && gpu.Name == name {
				gpu.Vram += ttBoardVramMib(name)
				break
			}
		}
	}

	// Convert map to slice
	var gpus []GpuInfo
	for _, key := range gpuKeys {
		gpus = append(gpus, *gpuMap[key])
	}

	// Reassign indices sequentially based on discovery order.
	for i := range gpus {
		gpus[i].Index = strconv.Itoa(i)
	}

	return gpus
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

	ttSmiSnapshot, err := unmarshalTtSmiSnapshot([]byte(res.Stdout))
	if err != nil {
		log.Error(ctx, "cannot read tt-smi json", "err", err)
		log.Debug(ctx, "tt-smi output", "stdout", res.Stdout)
		return gpus
	}

	return getGpusFromTtSmiSnapshot(ttSmiSnapshot)
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
			Vendor: gpu.GpuVendorIntel,
			Name:   strings.TrimSpace(record[0]),
			Vram:   vram,
			Index:  strings.TrimSpace(record[2]),
		})
	}
	return gpus
}
