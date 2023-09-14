package main

import (
	"context"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/shim"
	"github.com/dstackai/dstack/runner/internal/shim/backends"
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
	var dstackHome string

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
				Action: func(c *cli.Context, s string) error {
					for _, backend := range []string{"aws", "azure", "gcp", "lambda", "local"} {
						if s == backend {
							return nil
						}
					}
					return gerrors.Newf("unknown backend %s", s)
				},
			},
			&cli.PathFlag{
				Name:        "home",
				Usage:       "Dstack home directory",
				Destination: &dstackHome,
				EnvVars:     []string{"DSTACK_HOME"},
			},
			/* Runner Parameters */
			&cli.IntFlag{
				Name:        "runner-http-port",
				Usage:       "Set runner's http port",
				Value:       10999,
				Destination: &runnerParams.HttpPort,
				EnvVars:     []string{"DSTACK_RUNNER_HTTP_PORT"},
			},
			&cli.IntFlag{
				Name:        "runner-log-level",
				Usage:       "Set runner's log level",
				Value:       4,
				Destination: &runnerParams.LogLevel,
				EnvVars:     []string{"DSTACK_RUNNER_LOG_LEVEL"},
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
						FilePath:    "~/.ssh/authorized_keys", // todo check if user expand works
						Destination: &dockerParams.PublicSSHKey,
						EnvVars:     []string{"DSTACK_PUBLIC_SSH_KEY"},
					},
				},
				Action: func(c *cli.Context) error {
					log.Printf("Backend: %s\n", backendName)
					runnerParams.TempDir = "/tmp/runner"
					runnerParams.HomeDir = "/root"
					runnerParams.WorkingDir = "/workflow"
					log.Printf("Runner: %+v\n", runnerParams)

					var err error
					dockerParams.DstackHome, err = getDstackHome(dstackHome)
					if err != nil {
						return gerrors.Wrap(err)
					}
					log.Printf("Docker: %+v\n", dockerParams)

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
		backend, err := backends.NewBackend(context.TODO(), backendName)
		if err != nil {
			log.Fatal(err)
		}
		if err = backend.Terminate(context.TODO()); err != nil {
			log.Fatal(err)
		}
	}()

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
		return "", gerrors.Wrap(err)
	}
	return home + "/.dstack", nil
}
