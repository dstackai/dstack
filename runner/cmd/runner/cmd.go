package main

import (
	"log"
	"os"

	"github.com/urfave/cli/v2"
)

// Version is a build-time variable. The value is overridden by ldflags.
var Version string

func App() {
	var paths struct{ tempDir, homeDir, workingDir string }
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
						Required:    true,
						Destination: &paths.tempDir,
					},
					&cli.PathFlag{
						Name:        "home-dir",
						Usage:       "HomeDir directory for credentials and $HOME",
						Required:    true,
						Destination: &paths.homeDir,
					},
					&cli.PathFlag{
						Name:        "working-dir",
						Usage:       "Base path for the job",
						Required:    true,
						Destination: &paths.workingDir,
					},
					&cli.IntFlag{
						Name:        "http-port",
						Usage:       "Set a http port",
						Value:       10999,
						Destination: &httpPort,
					},
					&cli.IntFlag{
						Name:        "ssh-port",
						Usage:       "Set the ssh port",
						Required:    true,
						Destination: &sshPort,
					},
				},
				Action: func(c *cli.Context) error {
					err := start(paths.tempDir, paths.homeDir, paths.workingDir, httpPort, sshPort, logLevel, Version)
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
