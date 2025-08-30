package main

import (
	"log"
	"os"

	"github.com/dstackai/dstack/runner/consts"
	"github.com/urfave/cli/v2"
)

// Version is a build-time variable. The value is overridden by ldflags.
var Version string

func App() {
	var tempDir string
	var homeDir string
	var httpPort int
	var sshPort int
	var logLevel int

	app := &cli.App{
		Name:    "dstack-runner",
		Usage:   "configure and start dstack-runner",
		Version: Version,
		Flags: []cli.Flag{
			&cli.IntFlag{
				Name:        "log-level",
				Value:       2,
				DefaultText: "4 (Info)",
				Usage:       "log verbosity level: 2 (Error), 3 (Warning), 4 (Info), 5 (Debug), 6 (Trace)",
				Destination: &logLevel,
			},
		},
		Commands: []*cli.Command{
			{
				Name:  "start",
				Usage: "Start dstack-runner",
				Flags: []cli.Flag{
					&cli.PathFlag{
						Name:        "temp-dir",
						Usage:       "Temporary directory for logs and other files",
						Value:       consts.RunnerTempDir,
						Destination: &tempDir,
					},
					&cli.PathFlag{
						Name:        "home-dir",
						Usage:       "HomeDir directory for credentials and $HOME",
						Value:       consts.RunnerHomeDir,
						Destination: &homeDir,
					},
					// TODO: Not used, left for compatibility with old servers. Remove eventually.
					&cli.PathFlag{
						Name:        "working-dir",
						Hidden:      true,
						Destination: nil,
					},
					&cli.IntFlag{
						Name:        "http-port",
						Usage:       "Set a http port",
						Value:       consts.RunnerHTTPPort,
						Destination: &httpPort,
					},
					&cli.IntFlag{
						Name:        "ssh-port",
						Usage:       "Set the ssh port",
						Value:       consts.RunnerSSHPort,
						Destination: &sshPort,
					},
				},
				Action: func(c *cli.Context) error {
					err := start(tempDir, homeDir, httpPort, sshPort, logLevel, Version)
					if err != nil {
						return cli.Exit(err, 1)
					}
					return nil
				},
			},
		},
	}
	err := app.Run(os.Args)
	if err != nil {
		log.Fatal(err)
	}
}
