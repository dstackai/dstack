package main

import (
	"context"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/shim"
	"github.com/urfave/cli/v2"
	"log"
	"os"
)

func main() {
	var backendName string
	var runnerParams shim.RunnerParameters
	dockerParams := shim.DockerParameters{
		Runner:      &runnerParams,
		OpenSSHPort: 10022,
	}

	app := &cli.App{
		Name:    "dstack-shim",
		Usage:   "Starts dstack-runner or docker container. Kills the VM on exit.",
		Version: Version,
		Flags: []cli.Flag{
			&cli.StringFlag{
				Name:        "backend",
				Usage:       "Cloud backend provider",
				Required:    true,
				Destination: &backendName,
				EnvVars:     []string{"DSTACK_BACKEND"},
			},
			/* Runner Parameters */
			&cli.IntFlag{
				Name:        "http-port",
				Usage:       "Set runner's http port",
				Value:       10999,
				Destination: &runnerParams.HttpPort,
				EnvVars:     []string{"DSTACK_HTTP_PORT"},
			},
			&cli.IntFlag{
				Name:        "log-level",
				Usage:       "Set runner's log level",
				Value:       4,
				Destination: &runnerParams.LogLevel,
				EnvVars:     []string{"DSTACK_LOG_LEVEL"},
			},
			&cli.StringFlag{
				Name:        "runner-version",
				Usage:       "Set runner's version",
				Value:       "latest",
				Destination: &runnerParams.RunnerVersion,
				EnvVars:     []string{"DSTACK_RUNNER_VERSION"},
			},
			&cli.BoolFlag{
				Name:        "dev",
				Usage:       "Use stgn channel",
				Destination: &runnerParams.UseDev,
			},
		},
		Commands: []*cli.Command{
			{
				Name:  "docker",
				Usage: "Starts docker container and modifies entrypoint",
				Flags: []cli.Flag{
					/* Docker Parameters */
					&cli.BoolFlag{
						Name:        "with-auth",
						Usage:       "Waits for registry credentials",
						Destination: &dockerParams.WithAuth,
					},
					&cli.StringFlag{
						Name:        "image",
						Usage:       "Docker image name",
						Required:    true,
						Destination: &dockerParams.ImageName,
						EnvVars:     []string{"DSTACK_IMAGE_NAME"},
					},
					&cli.BoolFlag{
						Name:        "keep-container",
						Usage:       "Do not delete container on exit",
						Destination: &dockerParams.KeepContainer,
					},
					&cli.PathFlag{
						Name:        "ssh-key",
						Usage:       "Public SSH key",
						Required:    true,
						FilePath:    "~/.ssh/authorized_keys",
						Destination: &dockerParams.PublicSSHKey,
						EnvVars:     []string{"DSTACK_PUBLIC_SSH_KEY"},
					},
				},
				Action: func(c *cli.Context) error {
					log.Printf("Runner: %+v\n", runnerParams)
					log.Printf("Docker: %+v\n", dockerParams)
					return nil
					runnerParams.TempDir = "/tmp/runner" // todo mount on host?
					runnerParams.HomeDir = "/root"
					runnerParams.WorkingDir = "/workflow"
					return gerrors.Wrap(shim.RunDocker(context.TODO(), &dockerParams))
				},
			},
			{
				Name:  "subprocess",
				Usage: "Docker-less mode",
				Action: func(c *cli.Context) error {
					return gerrors.New("not implemented")
				},
			},
		},
	}

	defer func() {
		// todo kill VM
	}()

	if err := app.Run(os.Args); err != nil {
		log.Fatal(err)
	}
}
