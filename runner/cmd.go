package main

import (
	"fmt"
	"log"
	"os"
	"path/filepath"

	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/common"
	"github.com/urfave/cli/v2"

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
			&cli.StringFlag{
				Name:  "config-dir",
				Usage: "Set custom config dir",
				Value: filepath.Join(common.HomeDir(), ".dstack"),
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
					},
				},
				Action: func(c *cli.Context) error {
					start(c.Int("log-level"), c.Int("http-port"), c.String("config-dir"))
					return nil
				},
			},
			{
				Name:  "check",
				Usage: "Checking the system for the possibility to run the runner",
				Flags: []cli.Flag{},
				Action: func(c *cli.Context) error {
					return check(c.String("config-dir"))
				},
			},
		},
	}
	err := app.Run(os.Args)
	if err != nil {
		log.Fatal(err)
	}
}
