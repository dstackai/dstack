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
						Name:        "keep-container",
						Usage:       "Do not delete container on exit",
						Destination: &args.Docker.KeepContainer,
					},
					&cli.PathFlag{
						Name:        "ssh-key",
						Usage:       "Public SSH key",
						Required:    true,
						Destination: &args.Docker.PublicSSHKey,
						EnvVars:     []string{"DSTACK_PUBLIC_SSH_KEY"},
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
