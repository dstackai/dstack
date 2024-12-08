package shim

import (
	"context"
	"encoding/csv"
	"encoding/json"
	"errors"
	"io"
	"log"
	"os"
	"strconv"
	"strings"

	execute "github.com/alexellis/go-execute/v2"
)

const amdSmiImage = "un1def/amd-smi:6.2.2-0"

type GpuVendor string

const (
	NoVendor GpuVendor = "none"
	Nvidia   GpuVendor = "nvidia"
	Amd      GpuVendor = "amd"
)

type GpuInfo struct {
	Vendor GpuVendor
	Name   string
	Vram   int // MiB
}

func GetGpuVendor() GpuVendor {
	if _, err := os.Stat("/dev/kfd"); !errors.Is(err, os.ErrNotExist) {
		return Amd
	}
	if _, err := os.Stat("/dev/nvidiactl"); !errors.Is(err, os.ErrNotExist) {
		return Nvidia
	}
	return NoVendor
}

func GetGpuInfo() []GpuInfo {
	switch gpuVendor := GetGpuVendor(); gpuVendor {
	case Nvidia:
		return getNvidiaGpuInfo()
	case Amd:
		return getAmdGpuInfo()
	case NoVendor:
		return []GpuInfo{}
	}
	return []GpuInfo{}
}

func getNvidiaGpuInfo() []GpuInfo {
	gpus := []GpuInfo{}

	cmd := execute.ExecTask{
		Command:     "nvidia-smi",
		Args:        []string{"--query-gpu=gpu_name,memory.total", "--format=csv,nounits"},
		StreamStdio: false,
	}
	res, err := cmd.Execute(context.Background())
	if err != nil {
		log.Printf("failed to execute nvidia-smi: %s", err)
		return gpus
	}
	if res.ExitCode != 0 {
		log.Printf(
			"failed to execute nvidia-smi: exit code: %d: stdout: %s; stderr: %s",
			res.ExitCode, res.Stdout, res.Stderr,
		)
		return gpus
	}

	r := csv.NewReader(strings.NewReader(res.Stdout))
	// Skip header
	if _, err := r.Read(); err != nil {
		log.Printf("cannot read csv: %s", err)
		return gpus
	}
	for {
		record, err := r.Read()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			log.Printf("cannot read csv: %s", err)
			return gpus
		}
		if len(record) != 2 {
			log.Printf("two csv fields expected, got: %d", len(record))
			return gpus
		}
		vram, err := strconv.Atoi(strings.TrimSpace(record[1]))
		if err != nil {
			log.Printf("invalid VRAM value: %s", record[1])
			vram = 0
		}
		gpus = append(gpus, GpuInfo{
			Vendor: Nvidia,
			Name:   strings.TrimSpace(record[0]),
			Vram:   vram,
		})
	}
	return gpus
}

type amdGpu struct {
	Asic amdAsic `json:"asic"`
	Vram amdVram `json:"vram"`
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

func getAmdGpuInfo() []GpuInfo {
	gpus := []GpuInfo{}

	cmd := execute.ExecTask{
		Command: "docker",
		Args: []string{
			"run",
			"--rm",
			"--device", "/dev/kfd",
			"--device", "/dev/dri",
			amdSmiImage,
			"static", "--json", "--asic", "--vram",
		},
		StreamStdio: false,
	}
	res, err := cmd.Execute(context.Background())
	if err != nil {
		log.Printf("failed to execute amd-smi: %s", err)
		return gpus
	}
	if res.ExitCode != 0 {
		log.Printf(
			"failed to execute amd-smi: exit code: %d: stdout: %s; stderr: %s",
			res.ExitCode, res.Stdout, res.Stderr,
		)
		return gpus
	}

	var amdGpus []amdGpu
	if err := json.Unmarshal([]byte(res.Stdout), &amdGpus); err != nil {
		log.Printf("cannot read json: %s", err)
		return gpus
	}
	for _, amdGpu := range amdGpus {
		gpus = append(gpus, GpuInfo{
			Vendor: Amd,
			Name:   amdGpu.Asic.Name,
			Vram:   amdGpu.Vram.Size.Value,
		})
	}
	return gpus
}
