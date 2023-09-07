package main

import (
	"github.com/urfave/cli/v2"
	"log"
	"os"

	"github.com/dstackai/dstack/runner/version"
)

func App() {
	app := &cli.App{
		Name:    "dstack-runner",
		Usage:   "configure and start dstack-runner",
		Version: version.Version,
		Flags: []cli.Flag{
			&cli.IntFlag{
				Name:        "log-level",
				Value:       2,
				DefaultText: "4 (Info)",
				Usage:       "log verbosity level: 2 (Error), 3 (Warning), 4 (Info), 5 (Debug), 6 (Trace)",
			},
		},
		Commands: []*cli.Command{
			{
				Name:  "start",
				Usage: "Start dstack-runner",
				Flags: []cli.Flag{
					&cli.PathFlag{
						Name:     "working-dir",
						Usage:    "Base path for the job",
						Required: true,
					},
					&cli.PathFlag{
						Name:     "temp-dir",
						Usage:    "Temporary directory for logs and other files",
						Required: true,
					},
					&cli.StringFlag{
						Name:  "http-port",
						Usage: "Set a http port",
					},
				},
				Action: func(c *cli.Context) error {
					start(c.Int("log-level"), c.Int("http-port"), c.Path("working-dir"), c.Path("temp-dir"))
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
