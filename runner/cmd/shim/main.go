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
	"time"

	"github.com/sirupsen/logrus"
	"github.com/urfave/cli/v3"

	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/common"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/shim"
	"github.com/dstackai/dstack/runner/internal/shim/api"
	"github.com/dstackai/dstack/runner/internal/shim/components"
	"github.com/dstackai/dstack/runner/internal/shim/dcgm"
)

// Version is a build-time variable. The value is overridden by ldflags.
var Version string

func main() {
	os.Exit(mainInner())
}

func mainInner() int {
	var args shim.CLIArgs
	var serviceMode bool

	const defaultLogLevel = int(logrus.InfoLevel)

	log.DefaultEntry.Logger.SetLevel(logrus.Level(defaultLogLevel))
	log.DefaultEntry.Logger.SetOutput(os.Stderr)

	shimBinaryPath, err := os.Executable()
	if err != nil {
		shimBinaryPath = consts.ShimBinaryPath
	}

	cmd := &cli.Command{
		Name:    "dstack-shim",
		Usage:   "Starts dstack-runner or docker container.",
		Version: Version,
		Flags: []cli.Flag{
			/* Shim Parameters */
			&cli.StringFlag{
				Name:        "shim-home",
				Usage:       "Set shim's home directory",
				Destination: &args.Shim.HomeDir,
				TakesFile:   true,
				DefaultText: path.Join("~", consts.DstackDirPath),
				Sources:     cli.EnvVars("DSTACK_SHIM_HOME"),
			},
			&cli.StringFlag{
				Name:        "shim-binary-path",
				Usage:       "Path to shim's binary",
				Value:       shimBinaryPath,
				Destination: &args.Shim.BinaryPath,
				TakesFile:   true,
				Sources:     cli.EnvVars("DSTACK_SHIM_BINARY_PATH"),
			},
			&cli.IntFlag{
				Name:        "shim-http-port",
				Usage:       "Set shim's http port",
				Value:       10998,
				Destination: &args.Shim.HTTPPort,
				Sources:     cli.EnvVars("DSTACK_SHIM_HTTP_PORT"),
			},
			&cli.IntFlag{
				Name:        "shim-log-level",
				Usage:       "Set shim's log level",
				Value:       defaultLogLevel,
				Destination: &args.Shim.LogLevel,
				Sources:     cli.EnvVars("DSTACK_SHIM_LOG_LEVEL"),
			},
			/* Runner Parameters */
			&cli.StringFlag{
				Name:        "runner-download-url",
				Usage:       "Set runner's download URL",
				Destination: &args.Runner.DownloadURL,
				Sources:     cli.EnvVars("DSTACK_RUNNER_DOWNLOAD_URL"),
			},
			&cli.StringFlag{
				Name:        "runner-binary-path",
				Usage:       "Path to runner's binary",
				Value:       consts.RunnerBinaryPath,
				Destination: &args.Runner.BinaryPath,
				TakesFile:   true,
				Sources:     cli.EnvVars("DSTACK_RUNNER_BINARY_PATH"),
			},
			&cli.IntFlag{
				Name:        "runner-http-port",
				Usage:       "Set runner's http port",
				Value:       consts.RunnerHTTPPort,
				Destination: &args.Runner.HTTPPort,
				Sources:     cli.EnvVars("DSTACK_RUNNER_HTTP_PORT"),
			},
			&cli.IntFlag{
				Name:        "runner-ssh-port",
				Usage:       "Set runner's ssh port",
				Value:       consts.RunnerSSHPort,
				Destination: &args.Runner.SSHPort,
				Sources:     cli.EnvVars("DSTACK_RUNNER_SSH_PORT"),
			},
			&cli.IntFlag{
				Name:        "runner-log-level",
				Usage:       "Set runner's log level",
				Value:       defaultLogLevel,
				Destination: &args.Runner.LogLevel,
				Sources:     cli.EnvVars("DSTACK_RUNNER_LOG_LEVEL"),
			},
			/* DCGM Exporter Parameters */
			&cli.IntFlag{
				Name:        "dcgm-exporter-http-port",
				Usage:       "DCGM Exporter http port",
				Value:       10997,
				Destination: &args.DCGMExporter.HTTPPort,
				Sources:     cli.EnvVars("DSTACK_DCGM_EXPORTER_HTTP_PORT"),
			},
			&cli.IntFlag{
				Name:        "dcgm-exporter-interval",
				Usage:       "DCGM Exporter collect interval, milliseconds",
				Value:       5000,
				Destination: &args.DCGMExporter.Interval,
				Sources:     cli.EnvVars("DSTACK_DCGM_EXPORTER_INTERVAL"),
			},
			/* DCGM Parameters */
			&cli.StringFlag{
				Name:        "dcgm-address",
				Usage:       "nv-hostengine `hostname`, e.g., `localhost`",
				DefaultText: "start libdcgm in embedded mode",
				Destination: &args.DCGM.Address,
				Sources:     cli.EnvVars("DSTACK_DCGM_ADDRESS"),
			},
			/* Docker Parameters */
			&cli.BoolFlag{
				Name:        "privileged",
				Usage:       "Give extended privileges to the container",
				Destination: &args.Docker.Privileged,
				Sources:     cli.EnvVars("DSTACK_DOCKER_PRIVILEGED"),
			},
			&cli.StringFlag{
				Name:        "pjrt-device",
				Usage:       "Set the PJRT_DEVICE environment variable (e.g., TPU, GPU)",
				Destination: &args.Docker.PJRTDevice,
				Sources:     cli.EnvVars("PJRT_DEVICE"),
			},
			/* Misc Parameters */
			&cli.BoolFlag{
				Name:        "service",
				Usage:       "Start as a service",
				Destination: &serviceMode,
				Sources:     cli.EnvVars("DSTACK_SERVICE_MODE"),
			},
		},
		Action: func(ctx context.Context, cmd *cli.Command) error {
			return start(ctx, args, serviceMode)
		},
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	if err := cmd.Run(ctx, os.Args); err != nil {
		log.Error(ctx, err.Error())
		return 1
	}

	return 0
}

func start(ctx context.Context, args shim.CLIArgs, serviceMode bool) (err error) {
	log.DefaultEntry.Logger.SetLevel(logrus.Level(args.Shim.LogLevel))
	log.Info(ctx, "Starting dstack-shim", "version", Version)

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

	runnerManager, runnerErr := components.NewRunnerManager(ctx, args.Runner.BinaryPath)
	if args.Runner.DownloadURL != "" {
		if err := runnerManager.Install(ctx, args.Runner.DownloadURL, false); err != nil {
			return err
		}
	} else if runnerErr != nil {
		return runnerErr
	}
	shimManager, shimErr := components.NewShimManager(ctx, args.Shim.BinaryPath)
	if shimErr != nil {
		return shimErr
	}

	log.Debug(ctx, "Shim", "args", args.Shim)
	log.Debug(ctx, "Runner", "args", args.Runner)
	log.Debug(ctx, "Docker", "args", args.Docker)

	dockerRunner, err := shim.NewDockerRunner(ctx, &args)
	if err != nil {
		return err
	}

	var dcgmExporter *dcgm.DCGMExporter
	var dcgmWrapper dcgm.DCGMWrapperInterface

	if common.GetGpuVendor() == common.GpuVendorNvidia {
		dcgmExporterPath, err := dcgm.GetDCGMExporterExecPath(ctx)
		if err == nil {
			interval := time.Duration(args.DCGMExporter.Interval * int(time.Millisecond))
			dcgmExporter = dcgm.NewDCGMExporter(dcgmExporterPath, args.DCGMExporter.HTTPPort, interval)
			err = dcgmExporter.Start(ctx)
		}
		if err == nil {
			log.Info(ctx, "using DCGM Exporter")
			defer func() {
				if err := dcgmExporter.Stop(ctx); err != nil {
					log.Error(ctx, "failed to stop DCGM Exporter", "err", err)
				}
			}()
		} else {
			log.Warning(ctx, "not using DCGM Exporter", "err", err)
		}

		dcgmWrapper, err = dcgm.NewDCGMWrapper(args.DCGM.Address)
		if err == nil {
			log.Info(ctx, "using libdcgm")
			defer func() {
				if err := dcgmWrapper.Shutdown(); err != nil {
					log.Error(ctx, "failed to shut down libdcgm", "err", err)
				}
			}()
			if err := dcgmWrapper.EnableHealthChecks(); err != nil {
				log.Error(ctx, "failed to enable libdcgm health checks", "err", err)
			}
		} else {
			log.Warning(ctx, "not using libdcgm", "err", err)
		}
	}

	address := fmt.Sprintf("localhost:%d", args.Shim.HTTPPort)
	shimServer := api.NewShimServer(
		ctx, address, Version,
		dockerRunner, dcgmExporter, dcgmWrapper,
		runnerManager, shimManager,
	)

	if serviceMode {
		if err := shim.WriteHostInfo(shimHomeDir, dockerRunner.Resources(ctx)); err != nil {
			if errors.Is(err, os.ErrExist) {
				log.Error(ctx, "write host info: file already exists")
			} else {
				return fmt.Errorf("write host info: %w", err)
			}
		}
	}

	var serveErr error
	serveErrCh := make(chan error)

	go func() {
		if err := shimServer.Serve(); err != nil {
			serveErrCh <- err
		}
		close(serveErrCh)
	}()

	select {
	case serveErr = <-serveErrCh:
	case <-ctx.Done():
	}

	shutdownCtx, cancelShutdown := context.WithTimeout(ctx, 5*time.Second)
	defer cancelShutdown()
	shutdownErr := shimServer.Shutdown(shutdownCtx, false)
	if serveErr != nil {
		return serveErr
	}
	return shutdownErr
}
