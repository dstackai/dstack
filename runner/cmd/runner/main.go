package main

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/signal"
	"path"
	"path/filepath"
	"syscall"

	"github.com/sirupsen/logrus"
	"github.com/urfave/cli/v3"

	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/executor"
	linuxuser "github.com/dstackai/dstack/runner/internal/linux/user"
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
					// --home-dir is not used since 0.20.4, but the flag was retained as no-op
					// for compatibility with pre-0.20.4 shims; remove the flag eventually
					&cli.StringFlag{
						Name:   "home-dir",
						Hidden: true,
					},
				},
				Action: func(ctx context.Context, cmd *cli.Command) error {
					return start(ctx, tempDir, httpPort, sshPort, sshAuthorizedKeys, logLevel, Version)
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

func start(ctx context.Context, tempDir string, httpPort int, sshPort int, sshAuthorizedKeys []string, logLevel int, version string) error {
	if err := os.MkdirAll(tempDir, 0o755); err != nil {
		return fmt.Errorf("create temp directory: %w", err)
	}

	defaultLogFile, err := log.CreateAppendFile(filepath.Join(tempDir, consts.RunnerDefaultLogFileName))
	if err != nil {
		return fmt.Errorf("create default log file: %w", err)
	}
	defer func() {
		if err := defaultLogFile.Close(); err != nil {
			log.Error(ctx, "Failed to close default log file", "err", err)
		}
	}()
	log.DefaultEntry.Logger.SetOutput(io.MultiWriter(os.Stdout, defaultLogFile))
	log.DefaultEntry.Logger.SetLevel(logrus.Level(logLevel))

	currentUser, err := linuxuser.FromCurrentProcess()
	if err != nil {
		return fmt.Errorf("get current process user: %w", err)
	}
	if !currentUser.IsRoot() {
		return fmt.Errorf("must be root: %s", currentUser)
	}
	if currentUser.HomeDir == "" {
		log.Warning(ctx, "Current user does not have home dir, using /root as a fallback", "user", currentUser)
		currentUser.HomeDir = "/root"
	}
	// Fix the current process HOME, just in case some internals require it (e.g., they use os.UserHomeDir() or
	// spawn a child process which uses that variable)
	envHome, envHomeIsSet := os.LookupEnv("HOME")
	if envHome != currentUser.HomeDir {
		if !envHomeIsSet {
			log.Warning(ctx, "HOME is not set, setting the value", "home", currentUser.HomeDir)
		} else {
			log.Warning(ctx, "HOME is incorrect, fixing the value", "current", envHome, "home", currentUser.HomeDir)
		}
		if err := os.Setenv("HOME", currentUser.HomeDir); err != nil {
			return fmt.Errorf("set HOME: %w", err)
		}
	}
	log.Trace(ctx, "Running as", "user", currentUser)

	// NB: The Mkdir/Chown/Chmod code below relies on the fact that RunnerDstackDir path is _not_ nested (/dstack).
	// Adjust it if the path is changed to, e.g., /opt/dstack
	const dstackDir = consts.RunnerDstackDir
	dstackSshDir := path.Join(dstackDir, "ssh")

	// To ensure that all components of the authorized_keys path are owned by root and no directories
	// are group or world writable, as required by sshd with "StrictModes yes" (the default value),
	// we fix `/dstack` ownership and permissions and remove `/dstack/ssh` (it will be (re)created
	// in Sshd.Prepare())
	// See: https://github.com/openssh/openssh-portable/blob/d01efaa1c9ed84fd9011201dbc3c7cb0a82bcee3/misc.c#L2257-L2272
	if err := os.Mkdir(dstackDir, 0o755); errors.Is(err, os.ErrExist) {
		if err := os.Chown(dstackDir, 0, 0); err != nil {
			return fmt.Errorf("chown dstack dir: %w", err)
		}
		if err := os.Chmod(dstackDir, 0o755); err != nil {
			return fmt.Errorf("chmod dstack dir: %w", err)
		}
	} else if err != nil {
		return fmt.Errorf("create dstack dir: %w", err)
	}
	if err := os.RemoveAll(dstackSshDir); err != nil {
		return fmt.Errorf("remove dstack ssh dir: %w", err)
	}

	sshd := ssh.NewSshd("/usr/sbin/sshd")
	if err := sshd.Prepare(ctx, dstackSshDir, sshPort, "INFO"); err != nil {
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

	ex, err := executor.NewRunExecutor(tempDir, dstackDir, *currentUser, sshd)
	if err != nil {
		return fmt.Errorf("create executor: %w", err)
	}

	server, err := api.NewServer(ctx, fmt.Sprintf(":%d", httpPort), version, ex)
	if err != nil {
		return fmt.Errorf("create server: %w", err)
	}
	log.Trace(ctx, "Starting API server", "port", httpPort)
	if err := server.Run(ctx); err != nil {
		return fmt.Errorf("server failed: %w", err)
	}

	return nil
}
