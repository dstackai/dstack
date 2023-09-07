package main

import (
	"context"
	"fmt"
	"github.com/dstackai/dstack/runner/internal/api"
	"github.com/dstackai/dstack/runner/internal/executor"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/ports"
	"github.com/sirupsen/logrus"
	"io"
	_ "net/http/pprof"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"
)

func main() {
	App()
}

func start(logLevel int, httpPort int, workingDir string, tempDir string) {
	if err := os.MkdirAll(tempDir, 0755); err != nil {
		log.Error(context.TODO(), "Failed to create temp directory", "err", err)
		os.Exit(1)
	}
	defaultLogFile, err := log.CreateAppendFile(filepath.Join(tempDir, "default.log"))
	if err != nil {
		log.Error(context.TODO(), "Failed to create default log file", "err", err)
		os.Exit(1)
	}
	defer func() { _ = defaultLogFile.Close() }()
	log.DefaultEntry.Logger.SetOutput(io.MultiWriter(os.Stdout, defaultLogFile))
	log.DefaultEntry.Logger.SetLevel(logrus.Level(logLevel))

	if httpPort == 0 {
		for httpPort = 10999; httpPort >= 10000; httpPort-- {
			if vacant, _ := ports.CheckPort(httpPort); vacant {
				break
			}
		}
		if httpPort == 9999 {
			log.Error(context.TODO(), "Can't pick a vacant port for logs streaming")
			os.Exit(1)
		}
	}
	ctx := context.Background()
	server := api.NewServer(tempDir, fmt.Sprintf(":%d", httpPort))

	runnerLogFile, err := log.CreateAppendFile(filepath.Join(tempDir, "runner.log"))
	if err != nil {
		log.Error(context.TODO(), "Failed to create runner log file", "err", err)
		os.Exit(1)
	}
	defer func() { _ = runnerLogFile.Close() }()
	runnerLogger := log.NewEntry(io.MultiWriter(os.Stdout, runnerLogFile, server.RunnerLogsWriter()), logLevel)
	runnerCtx := log.WithLogger(ctx, runnerLogger)

	go func() {
		log.Trace(context.TODO(), "Starting API server", "port", httpPort)
		if err := server.Run(); err != nil {
			log.Error(context.TODO(), "Server exited or failed", "err", err)
		}
	}()
	ctxSig, cancel := signal.NotifyContext(runnerCtx, os.Interrupt, syscall.SIGTERM, syscall.SIGKILL, syscall.SIGQUIT)
	go func() {
		select {
		case <-server.JobTerminated():
			log.Info(runnerCtx, "Job was terminated via API")
			cancel()
		}
	}()

	log.Info(runnerCtx, fmt.Sprintf("Log level: %v", runnerLogger.Logger.Level.String()))

	jobLogFile, err := log.CreateAppendFile(filepath.Join(tempDir, "runner.log"))
	if err != nil {
		log.Error(context.TODO(), "Failed to create runner log file", "err", err)
		os.Exit(1)
	}
	defer func() { _ = jobLogFile.Close() }()
	ex := executor.NewExecutor(workingDir, io.MultiWriter(jobLogFile, server.JobLogsWriter()), server.GetAdapter())

	log.Trace(runnerCtx, "Starting executor")
	if err := ex.Run(ctxSig); err != nil {
		log.Error(runnerCtx, "Executor failed", "err", err)
	}
	cancel()

	select {
	case <-server.Done():
		log.Info(context.TODO(), "Server finished normally")
	case <-time.After(10 * time.Second):
		log.Info(runnerCtx, "Timeout waiting for clients to pull logs")
	}
}
