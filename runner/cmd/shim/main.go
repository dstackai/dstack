package main

import (
	"context"
	"encoding/csv"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	execute "github.com/alexellis/go-execute/v2"
	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/shim"
	"github.com/dstackai/dstack/runner/internal/shim/api"
	"github.com/shirou/gopsutil/v3/mem"
	"github.com/urfave/cli/v2"
	"golang.org/x/sys/unix"
)

// Version is a build-time variable. The value is overridden by ldflags.
var Version string

func main() {
	var args shim.CLIArgs
	args.Docker.SSHPort = 10022
	var serviceMode bool

	app := &cli.App{
		Name:    "dstack-shim",
		Usage:   "Starts dstack-runner or docker container.",
		Version: Version,
		Flags: []cli.Flag{
			/* Shim Parameters */
			&cli.PathFlag{
				Name:        "home",
				Usage:       "Dstack home directory",
				Destination: &args.Shim.HomeDir,
				EnvVars:     []string{"DSTACK_HOME"},
			},
			&cli.IntFlag{
				Name:        "shim-http-port",
				Usage:       "Set's shim's http port",
				Value:       10998,
				Destination: &args.Shim.HTTPPort,
				EnvVars:     []string{"DSTACK_SHIM_HTTP_PORT"},
			},
			/* Runner Parameters */
			&cli.IntFlag{
				Name:        "runner-http-port",
				Usage:       "Set runner's http port",
				Value:       10999,
				Destination: &args.Runner.HTTPPort,
				EnvVars:     []string{"DSTACK_RUNNER_HTTP_PORT"},
			},
			&cli.IntFlag{
				Name:        "runner-log-level",
				Usage:       "Set runner's log level",
				Value:       4,
				Destination: &args.Runner.LogLevel,
				EnvVars:     []string{"DSTACK_RUNNER_LOG_LEVEL"},
			},
			&cli.StringFlag{
				Name:        "runner-version",
				Usage:       "Set runner's version",
				Value:       "latest",
				Destination: &args.Runner.Version,
				EnvVars:     []string{"DSTACK_RUNNER_VERSION"},
			},
			&cli.BoolFlag{
				Name:        "dev",
				Usage:       "Use stgn channel",
				Destination: &args.Runner.DevChannel,
			},
			&cli.PathFlag{
				Name:        "runner-binary-path",
				Usage:       "Path to runner's binary",
				Destination: &args.Runner.BinaryPath,
				EnvVars:     []string{"DSTACK_RUNNER_BINARY_PATH"},
			},
		},
		Commands: []*cli.Command{
			{
				Name:  "docker",
				Usage: "Starts docker container and modifies entrypoint",
				Flags: []cli.Flag{
					/* Docker Parameters */
					&cli.BoolFlag{
						Name:        "privileged",
						Usage:       "Give extended privileges to the container",
						Destination: &args.Docker.Privileged,
					},
					&cli.StringFlag{
						Name:        "ssh-key",
						Usage:       "Public SSH key",
						Required:    true,
						Destination: &args.Docker.ConcatinatedPublicSSHKeys,
						EnvVars:     []string{"DSTACK_PUBLIC_SSH_KEY"},
					},
					&cli.StringFlag{
						Name:        "pjrt-device",
						Usage:       "Set the PJRT_DEVICE environment variable (e.g., TPU, GPU)",
						Destination: &args.Docker.PJRTDevice,
						EnvVars:     []string{"PJRT_DEVICE"},
					},
					&cli.BoolFlag{
						Name:        "service",
						Usage:       "Start as a service",
						Destination: &serviceMode,
						EnvVars:     []string{"DSTACK_SERVICE_MODE"},
					},
				},
				Action: func(c *cli.Context) error {
					if args.Runner.BinaryPath == "" {
						if err := args.DownloadRunner(); err != nil {
							return cli.Exit(err, 1)
						}
					}

					args.Runner.TempDir = "/tmp/runner"
					args.Runner.HomeDir = "/root"
					args.Runner.WorkingDir = "/workflow"

					var err error

					// set dstack home path
					args.Shim.HomeDir, err = getDstackHome(args.Shim.HomeDir)
					if err != nil {
						return cli.Exit(err, 1)
					}
					log.Printf("Config Shim: %+v\n", args.Shim)
					log.Printf("Config Runner: %+v\n", args.Runner)
					log.Printf("Config Docker: %+v\n", args.Docker)

					dockerRunner, err := shim.NewDockerRunner(args)
					if err != nil {
						return cli.Exit(err, 1)
					}

					address := fmt.Sprintf(":%d", args.Shim.HTTPPort)
					shimServer := api.NewShimServer(address, dockerRunner, Version)

					defer func() {
						shutdownCtx, cancelShutdown := context.WithTimeout(context.Background(), 5*time.Second)
						defer cancelShutdown()
						_ = shimServer.HttpServer.Shutdown(shutdownCtx)
					}()

					if serviceMode {
						writeHostInfo()
					}

					if err := shimServer.HttpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
						return cli.Exit(err, 1)
					}

					return nil
				},
			},
		},
	}

	if err := app.Run(os.Args); err != nil {
		log.Fatal(err)
	}
}

func getDstackHome(flag string) (string, error) {
	if flag != "" {
		return flag, nil
	}

	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(home, consts.DstackDirPath), nil
}

func writeHostInfo() {
	// host_info exist
	if _, err := os.Stat(consts.HostInfoFile); !errors.Is(err, os.ErrNotExist) {
		return
	}

	type Message struct {
		GpuName   string   `json:"gpu_name"`
		GpuMemory string   `json:"gpu_memory"`
		GpuCount  int      `json:"gpu_count"`
		Adresses  []string `json:"addresses"`
		DiskSize  uint64   `json:"disk_size"`
		NumCPUs   int      `json:"cpus"`
		Memory    uint64   `json:"memory"`
	}

	gpuCount := 0
	gpuMemory := ""
	gpuName := ""
	gpus := getGpuInfo()
	if len(gpus) != 0 {
		gpuCount = len(gpus)
		gpuMemory = gpus[0][1]
		gpuName = gpus[0][0]
	}
	m := Message{
		GpuName:   gpuName,
		GpuMemory: gpuMemory,
		GpuCount:  gpuCount,
		Adresses:  getInterfaces(),
		DiskSize:  getDiskSize(),
		NumCPUs:   runtime.NumCPU(),
		Memory:    getMemory(),
	}

	b, err := json.Marshal(m)
	if err != nil {
		panic(err)
	}

	f, err := os.Create(consts.HostInfoFile)
	if err != nil {
		panic(err)
	}
	defer f.Close()

	_, err = f.Write(b)
	if err != nil {
		panic(err)
	}

	err = f.Sync()
	if err != nil {
		panic(err)
	}
}

func getGpuInfo() [][]string {
	cmd := execute.ExecTask{
		Command: "docker",
		Args: []string{
			"run",
			"--rm",
			"--gpus", "all",
			"dstackai/base:py3.12-0.5-cuda-12.1",
			"nvidia-smi", "--query-gpu=gpu_name,memory.total", "--format=csv",
		},
		StreamStdio: false,
	}

	res, err := cmd.Execute(context.Background())
	if err != nil {
		return [][]string{} // GPU not found
	}

	if res.ExitCode != 0 {
		return [][]string{} // GPU not found
	}

	r := csv.NewReader(strings.NewReader(res.Stdout))

	var gpus [][]string

	// Skip header
	if _, err := r.Read(); err != nil {
		panic("canot read csv")
	}

	for {
		record, err := r.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			log.Fatal(err)
		}

		gpus = append(gpus, record)
	}
	return gpus
}

func getInterfaces() []string {
	var addresses []string
	ifaces, err := net.Interfaces()
	if err != nil {
		panic("cannot get interfaces")
	}

	for _, i := range ifaces {
		addrs, err := i.Addrs()
		if err != nil {
			panic("cannot get addrs")
		}

		for _, addr := range addrs {
			switch v := addr.(type) {
			case *net.IPNet:
				if v.IP.IsLoopback() {
					continue
				}

				addresses = append(addresses, addr.String())
			}
		}
	}
	return addresses
}

func getDiskSize() uint64 {
	var stat unix.Statfs_t
	wd, err := os.Getwd()
	if err != nil {
		panic("cannot get current disk")
	}
	err = unix.Statfs(wd, &stat)
	if err != nil {
		panic("cannot get disk size")
	}
	size := stat.Bavail * uint64(stat.Bsize)
	return size
}

func getMemory() uint64 {
	v, err := mem.VirtualMemory()
	if err != nil {
		panic("cannot get emeory")
	}
	return v.Total
}
