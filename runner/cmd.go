package main

import (
	"fmt"
	"log"
	"os"

	"github.com/urfave/cli/v2"
	"gitlab.com/dstackai/dstackai-runner/consts"

	"gitlab.com/dstackai/dstackai-runner/version"
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
				Name:  "config",
				Usage: "configure dstack-runner",
				Flags: []cli.Flag{
					&cli.StringFlag{
						Name:     "token",
						Aliases:  []string{"t"},
						Usage:    "Set a personal access token",
						Required: true,
					},
					&cli.StringFlag{
						Name:     "server",
						Aliases:  []string{"s"},
						Usage:    fmt.Sprintf("Set a server endpoint, by default is %s", consts.ServerUrl),
						Required: false,
					},
					&cli.StringFlag{
						Name:     "hostname",
						Aliases:  []string{"host"},
						Usage:    "Set a hostname for runner",
						Required: false,
					},
				},
				Action: func(c *cli.Context) error {
					return nil
				},
			},
			{
				Name:  "start",
				Usage: "start dstack-runner",
				Flags: []cli.Flag{
					&cli.StringFlag{
						Name:    "http-port",
						Aliases: []string{"http"},
						Usage:   "Set a http port",
						Value:   "80",
					},
				},
				Action: func(c *cli.Context) error {
					start(c.Int("log-level"), c.Int("http-port"))

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
