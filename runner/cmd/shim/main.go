package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/shim"
	"github.com/dstackai/dstack/runner/internal/shim/api"
	"github.com/urfave/cli/v2"
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

					args.Runner.HomeDir = "/root"
					args.Runner.WorkingDir = "/workflow"

					var err error

					shimHomeDir := args.Shim.HomeDir
					if shimHomeDir == "" {
						home, err := os.UserHomeDir()
						if err != nil {
							return cli.Exit(err, 1)
						}
						shimHomeDir = filepath.Join(home, consts.DstackDirPath)
						args.Shim.HomeDir = shimHomeDir
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
						if err := shim.WriteHostInfo(shimHomeDir, dockerRunner.Resources()); err != nil {
							if errors.Is(err, os.ErrExist) {
								log.Println("cannot write host info: file already exists")
							} else {
								return cli.Exit(err, 1)
							}
						}
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
