package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"time"

	docker "github.com/docker/docker/client"
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
				Name:        "runner-download-url",
				Usage:       "Set runner's download URL",
				Destination: &args.Runner.DownloadURL,
				EnvVars:     []string{"DSTACK_RUNNER_DOWNLOAD_URL"},
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
						EnvVars:     []string{"DSTACK_DOCKER_PRIVILEGED"},
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

					dockerRunner, err := shim.NewDockerRunner(&args)
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
		GpuVendor shim.GpuVendor `json:"gpu_vendor"`
		GpuName   string         `json:"gpu_name"`
		GpuMemory int            `json:"gpu_memory"` // MiB
		GpuCount  int            `json:"gpu_count"`
		Addresses []string       `json:"addresses"`
		DiskSize  uint64         `json:"disk_size"` // bytes
		NumCPUs   int            `json:"cpus"`
		Memory    uint64         `json:"memory"` // bytes
	}

	gpuVendor := shim.NoVendor
	gpuCount := 0
	gpuMemory := 0
	gpuName := ""
	gpus := shim.GetGpuInfo()
	if len(gpus) != 0 {
		gpuCount = len(gpus)
		gpuVendor = gpus[0].Vendor
		gpuMemory = gpus[0].Vram
		gpuName = gpus[0].Name
	}
	m := Message{
		GpuVendor: gpuVendor,
		GpuName:   gpuName,
		GpuMemory: gpuMemory,
		GpuCount:  gpuCount,
		Addresses: getInterfaces(),
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
	client, err := docker.NewClientWithOpts(docker.FromEnv, docker.WithAPIVersionNegotiation())
	if err != nil {
		panic("cannot instantiate Docker client")
	}
	defer client.Close()
	info, err := client.Info(context.TODO())
	if err != nil {
		panic("cannot get Docker info")
	}
	var stat unix.Statfs_t
	err = unix.Statfs(info.DockerRootDir, &stat)
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
