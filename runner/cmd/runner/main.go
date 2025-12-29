package main

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"

	"github.com/sirupsen/logrus"
	"github.com/urfave/cli/v3"

	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/runner/api"
	"github.com/dstackai/dstack/runner/internal/ssh"
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
	var sshAuthorizedKeys []string
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
					&cli.StringSliceFlag{
						Name:        "ssh-authorized-key",
						Usage:       "dstack server or user authorized key. May be specified multiple times",
						Destination: &sshAuthorizedKeys,
					},
				},
				Action: func(ctx context.Context, cmd *cli.Command) error {
					return start(ctx, tempDir, homeDir, httpPort, sshPort, sshAuthorizedKeys, logLevel, Version)
				},
			},
		},
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM, syscall.SIGQUIT)
	defer stop()

	if err := cmd.Run(ctx, os.Args); err != nil {
		log.Error(ctx, err.Error())
		return 1
	}

	return 0
}

func start(ctx context.Context, tempDir string, homeDir string, httpPort int, sshPort int, sshAuthorizedKeys []string, logLevel int, version string) error {
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

	// To ensure that all components of the authorized_keys path are owned by root and no directories
	// are group or world writable, as required by sshd with "StrictModes yes" (the default value),
	// we fix `/dstack` ownership and permissions and remove `/dstack/ssh` (it will be (re)created
	// in Sshd.Prepare())
	// See: https://github.com/openssh/openssh-portable/blob/d01efaa1c9ed84fd9011201dbc3c7cb0a82bcee3/misc.c#L2257-L2272
	if err := os.Mkdir("/dstack", 0o755); errors.Is(err, os.ErrExist) {
		if err := os.Chown("/dstack", 0, 0); err != nil {
			return fmt.Errorf("chown dstack dir: %w", err)
		}
		if err := os.Chmod("/dstack", 0o755); err != nil {
			return fmt.Errorf("chmod dstack dir: %w", err)
		}
	} else if err != nil {
		return fmt.Errorf("create dstack dir: %w", err)
	}
	if err := os.RemoveAll("/dstack/ssh"); err != nil {
		return fmt.Errorf("remove dstack ssh dir: %w", err)
	}

	sshd := ssh.NewSshd("/usr/sbin/sshd")
	if err := sshd.Prepare(ctx, "/dstack/ssh", sshPort, "INFO"); err != nil {
		return fmt.Errorf("prepare sshd: %w", err)
	}
	if err := sshd.AddAuthorizedKeys(ctx, sshAuthorizedKeys...); err != nil {
		return fmt.Errorf("add authorized keys: %w", err)
	}
	if err := sshd.Start(ctx); err != nil {
		return fmt.Errorf("start sshd: %w", err)
	}
	defer func() {
		if err := sshd.Stop(ctx); err != nil {
			log.Error(ctx, "Error while stopping sshd", "err", err)
		}
	}()

	server, err := api.NewServer(ctx, tempDir, homeDir, fmt.Sprintf(":%d", httpPort), sshd, version)
	if err != nil {
		return fmt.Errorf("create server: %w", err)
	}
	log.Trace(ctx, "Starting API server", "port", httpPort)
	if err := server.Run(ctx); err != nil {
		return fmt.Errorf("server failed: %w", err)
	}

	return nil
}
