package main

import (
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"

	"github.com/sirupsen/logrus"
	"github.com/urfave/cli/v3"

	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/runner/api"
)

// Version is a build-time variable. The value is overridden by ldflags.
var Version string

func main() {
	os.Exit(mainInner())
}

func mainInner() int {
	var tempDir string
	var homeDir string
	var httpPort int
	var sshPort int
	var logLevel int

	cmd := &cli.Command{
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
					&cli.StringFlag{
						Name:        "temp-dir",
						Usage:       "Temporary directory for logs and other files",
						Value:       consts.RunnerTempDir,
						Destination: &tempDir,
						TakesFile:   true,
					},
					&cli.StringFlag{
						Name:        "home-dir",
						Usage:       "HomeDir directory for credentials and $HOME",
						Value:       consts.RunnerHomeDir,
						Destination: &homeDir,
						TakesFile:   true,
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
				Action: func(cxt context.Context, cmd *cli.Command) error {
					return start(cxt, tempDir, homeDir, httpPort, sshPort, logLevel, Version)
				},
			},
		},
	}

	ctx := context.Background()

	if err := cmd.Run(ctx, os.Args); err != nil {
		log.Error(ctx, err.Error())
		return 1
	}

	return 0
}

func start(ctx context.Context, tempDir string, homeDir string, httpPort int, sshPort int, logLevel int, version string) error {
	if err := os.MkdirAll(tempDir, 0o755); err != nil {
		return fmt.Errorf("create temp directory: %w", err)
	}

	defaultLogFile, err := log.CreateAppendFile(filepath.Join(tempDir, consts.RunnerDefaultLogFileName))
	if err != nil {
		return fmt.Errorf("create default log file: %w", err)
	}
	defer func() {
		closeErr := defaultLogFile.Close()
		if closeErr != nil {
			log.Error(ctx, "Failed to close default log file", "err", closeErr)
		}
	}()

	log.DefaultEntry.Logger.SetOutput(io.MultiWriter(os.Stdout, defaultLogFile))
	log.DefaultEntry.Logger.SetLevel(logrus.Level(logLevel))

	server, err := api.NewServer(ctx, tempDir, homeDir, fmt.Sprintf(":%d", httpPort), sshPort, version)
	if err != nil {
		return fmt.Errorf("create server: %w", err)
	}

	log.Trace(ctx, "Starting API server", "port", httpPort)
	if err := server.Run(ctx); err != nil {
		return fmt.Errorf("server failed: %w", err)
	}

	return nil
}
