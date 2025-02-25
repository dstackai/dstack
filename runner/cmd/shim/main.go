package main

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path"
	"path/filepath"
	"time"

	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/shim"
	"github.com/dstackai/dstack/runner/internal/shim/api"
	"github.com/dstackai/dstack/runner/internal/shim/dcgm"
	"github.com/dstackai/dstack/runner/internal/shim/host"
	"github.com/sirupsen/logrus"
	"github.com/urfave/cli/v2"
)

// Version is a build-time variable. The value is overridden by ldflags.
var Version string

func main() {
	var args shim.CLIArgs
	var serviceMode bool

	const defaultLogLevel = int(logrus.InfoLevel)

	ctx := context.Background()

	log.DefaultEntry.Logger.SetLevel(logrus.Level(defaultLogLevel))
	log.DefaultEntry.Logger.SetOutput(os.Stderr)

	app := &cli.App{
		Name:    "dstack-shim",
		Usage:   "Starts dstack-runner or docker container.",
		Version: Version,
		Flags: []cli.Flag{
			/* Shim Parameters */
			&cli.PathFlag{
				Name:        "shim-home",
				Usage:       "Set shim's home directory",
				Destination: &args.Shim.HomeDir,
				DefaultText: path.Join("~", consts.DstackDirPath),
				EnvVars:     []string{"DSTACK_SHIM_HOME"},
			},
			&cli.IntFlag{
				Name:        "shim-http-port",
				Usage:       "Set shim's http port",
				Value:       10998,
				Destination: &args.Shim.HTTPPort,
				EnvVars:     []string{"DSTACK_SHIM_HTTP_PORT"},
			},
			&cli.IntFlag{
				Name:        "shim-log-level",
				Usage:       "Set shim's log level",
				Value:       defaultLogLevel,
				Destination: &args.Shim.LogLevel,
				EnvVars:     []string{"DSTACK_SHIM_LOG_LEVEL"},
			},
			/* Runner Parameters */
			&cli.StringFlag{
				Name:        "runner-download-url",
				Usage:       "Set runner's download URL",
				Destination: &args.Runner.DownloadURL,
				EnvVars:     []string{"DSTACK_RUNNER_DOWNLOAD_URL"},
			},
			&cli.PathFlag{
				Name:        "runner-binary-path",
				Usage:       "Path to runner's binary",
				Value:       consts.RunnerBinaryPath,
				Destination: &args.Runner.BinaryPath,
				EnvVars:     []string{"DSTACK_RUNNER_BINARY_PATH"},
			},
			&cli.IntFlag{
				Name:        "runner-http-port",
				Usage:       "Set runner's http port",
				Value:       10999,
				Destination: &args.Runner.HTTPPort,
				EnvVars:     []string{"DSTACK_RUNNER_HTTP_PORT"},
			},
			&cli.IntFlag{
				Name:        "runner-ssh-port",
				Usage:       "Set runner's ssh port",
				Value:       10022,
				Destination: &args.Runner.SSHPort,
				EnvVars:     []string{"DSTACK_RUNNER_SSH_PORT"},
			},
			&cli.IntFlag{
				Name:        "runner-log-level",
				Usage:       "Set runner's log level",
				Value:       defaultLogLevel,
				Destination: &args.Runner.LogLevel,
				EnvVars:     []string{"DSTACK_RUNNER_LOG_LEVEL"},
			},
			/* DCGM Exporter Parameters */
			&cli.IntFlag{
				Name:        "dcgm-exporter-http-port",
				Usage:       "DCGM Exporter http port",
				Value:       10997,
				Destination: &args.DCGMExporter.HTTPPort,
				EnvVars:     []string{"DSTACK_DCGM_EXPORTER_HTTP_PORT"},
			},
			&cli.IntFlag{
				Name:        "dcgm-exporter-interval",
				Usage:       "DCGM Exporter collect interval, milliseconds",
				Value:       5000,
				Destination: &args.DCGMExporter.Interval,
				EnvVars:     []string{"DSTACK_DCGM_EXPORTER_INTERVAL"},
			},
			/* Docker Parameters */
			&cli.BoolFlag{
				Name:        "privileged",
				Usage:       "Give extended privileges to the container",
				Destination: &args.Docker.Privileged,
				EnvVars:     []string{"DSTACK_DOCKER_PRIVILEGED"},
			},
			&cli.StringFlag{
				Name:        "ssh-key",
				Usage:       "Public SSH key",
				Destination: &args.Docker.ConcatinatedPublicSSHKeys,
				EnvVars:     []string{"DSTACK_PUBLIC_SSH_KEY"},
			},
			&cli.StringFlag{
				Name:        "pjrt-device",
				Usage:       "Set the PJRT_DEVICE environment variable (e.g., TPU, GPU)",
				Destination: &args.Docker.PJRTDevice,
				EnvVars:     []string{"PJRT_DEVICE"},
			},
			/* Misc Parameters */
			&cli.BoolFlag{
				Name:        "service",
				Usage:       "Start as a service",
				Destination: &serviceMode,
				EnvVars:     []string{"DSTACK_SERVICE_MODE"},
			},
		},
		Action: func(c *cli.Context) error {
			return start(ctx, args, serviceMode)
		},
	}

	if err := app.Run(os.Args); err != nil {
		log.Fatal(ctx, err.Error())
	}
}

func start(ctx context.Context, args shim.CLIArgs, serviceMode bool) (err error) {
	log.DefaultEntry.Logger.SetLevel(logrus.Level(args.Shim.LogLevel))

	shimHomeDir := args.Shim.HomeDir
	if shimHomeDir == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return err
		}
		shimHomeDir = filepath.Join(home, consts.DstackDirPath)
		args.Shim.HomeDir = shimHomeDir
	}

	shimLogFile, err := log.CreateAppendFile(filepath.Join(shimHomeDir, consts.ShimLogFileName))
	if err != nil {
		return fmt.Errorf("failed to create shim log file: %w", err)
	}
	defer func() {
		_ = shimLogFile.Close()
	}()

	originalLogger := log.GetLogger(ctx)
	loggerOut := io.MultiWriter(originalLogger.Logger.Out, shimLogFile)
	ctx = log.WithLogger(ctx, log.NewEntry(loggerOut, int(originalLogger.Logger.GetLevel())))

	defer func() {
		// Should be called _before_ we close shimLogFile
		// If an error occurs earlier, we still log it to stderr in the main function
		if err != nil {
			log.Error(ctx, err.Error())
		}
	}()

	if err := args.DownloadRunner(ctx); err != nil {
		return err
	}

	log.Debug(ctx, "Shim", "args", args.Shim)
	log.Debug(ctx, "Runner", "args", args.Runner)
	log.Debug(ctx, "Docker", "args", args.Docker)

	dockerRunner, err := shim.NewDockerRunner(ctx, &args)
	if err != nil {
		return err
	}

	var dcgmExporter *dcgm.DCGMExporter

	if host.GetGpuVendor() == host.GpuVendorNvidia {
		dcgmExporterPath, err := dcgm.GetDCGMExporterExecPath(ctx)
		if err == nil {
			interval := time.Duration(args.DCGMExporter.Interval * int(time.Millisecond))
			dcgmExporter = dcgm.NewDCGMExporter(dcgmExporterPath, args.DCGMExporter.HTTPPort, interval)
			err = dcgmExporter.Start(ctx)
		}
		if err == nil {
			log.Info(ctx, "using DCGM Exporter")
			defer func() {
				_ = dcgmExporter.Stop(ctx)
			}()
		} else {
			log.Warning(ctx, "not using DCGM Exporter", "err", err)
			dcgmExporter = nil
		}
	}

	address := fmt.Sprintf(":%d", args.Shim.HTTPPort)
	shimServer := api.NewShimServer(ctx, address, dockerRunner, dcgmExporter, Version)

	defer func() {
		shutdownCtx, cancelShutdown := context.WithTimeout(ctx, 5*time.Second)
		defer cancelShutdown()
		_ = shimServer.HttpServer.Shutdown(shutdownCtx)
	}()

	if serviceMode {
		if err := shim.WriteHostInfo(shimHomeDir, dockerRunner.Resources(ctx)); err != nil {
			if errors.Is(err, os.ErrExist) {
				log.Error(ctx, "cannot write host info: file already exists")
			} else {
				return err
			}
		}
	}

	if err := shimServer.HttpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		return err
	}

	return nil
}
