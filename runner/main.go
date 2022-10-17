package main

import (
	"bytes"
	"context"
	"fmt"
	_ "net/http/pprof"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/dstackai/dstackai/runner/consts"
	"github.com/dstackai/dstackai/runner/internal/backend"
	_ "github.com/dstackai/dstackai/runner/internal/backend/local"
	_ "github.com/dstackai/dstackai/runner/internal/backend/s3"
	"github.com/dstackai/dstackai/runner/internal/common"
	"github.com/dstackai/dstackai/runner/internal/container"
	"github.com/dstackai/dstackai/runner/internal/executor"
	"github.com/dstackai/dstackai/runner/internal/log"
	"github.com/dstackai/dstackai/runner/internal/stream"
	"github.com/sirupsen/logrus"
)

func main() {
	App()
}

func start(logLevel int, httpPort int) {
	ctx := context.Background()
	log.L.Logger.SetLevel(logrus.Level(logLevel))
	fileLog, err := os.OpenFile("/var/log/dstack/output.log", os.O_RDWR|os.O_CREATE|os.O_APPEND, 0o777)
	if err == nil {
		log.L.Logger.SetOutput(fileLog)
	}
	logCtx := log.WithLogger(ctx, log.L)
	log.Info(logCtx, fmt.Sprintf("Log level: %v", log.L.Logger.GetLevel().String()))
	log.Info(logCtx, "RUNNER START...")

	common.CreateTMPDir()

	pathConfig := filepath.Join(common.HomeDir(), consts.DSTACK_DIR_PATH, consts.CONFIG_FILE_NAME)

	b, err := backend.New(logCtx, pathConfig)
	if err != nil {
		log.L.Error("[ERROR]", err)
		os.Exit(1)
	}
	streamLogs := stream.New(httpPort)
	go func() {
		err := streamLogs.Run(logCtx)
		if err != nil {
			log.Error(logCtx, "Failed stream log", "err", err)
		}
	}()

	ex := executor.New(b)
	ex.SetStreamLogs(streamLogs)

	ctxSig, cancel := signal.NotifyContext(logCtx, os.Interrupt, syscall.SIGTERM, syscall.SIGKILL)

	defer ex.Shutdown(context.Background())

	err = ex.Init(ctxSig)
	if err != nil {
		log.Error(logCtx, "Failed to init executor", "err", err)
		cancel()

	}
	// Also temporary logic during transition
	wg := sync.WaitGroup{}
	wg.Add(1)

	go func() {
		if err = ex.Run(ctxSig); err != nil {
			log.Error(logCtx, "dstack-runner ended with an error: ", err)
		}
		wg.Done()
	}()
	wg.Wait()

	cancel()
	time.Sleep(1 * time.Second) // TODO: ugly hack. Need wait for buf cloudwatch
}

func check() {
	ctx := context.Background()
	engine := container.NewEngine()
	if engine == nil {
		printErrorAndExit("Docker is not installed")
	}
	if engine.DockerRuntime() != consts.NVIDIA_RUNTIME {
		printErrorAndExit("NVIDIA docker is not installed")
	}
	var logger bytes.Buffer
	docker, err := engine.Create(ctx,
		&container.Spec{
			Image:    consts.NVIDIA_CUDA_IMAGE,
			Commands: strings.Split(consts.NVIDIA_SMI_CMD, " "),
		},
		&logger)
	if err != nil {
		printErrorAndExit("Failed to create docker container: " + err.Error())
	}
	err = docker.Run(ctx)
	if err != nil {
		if strings.Contains(err.Error(), consts.NVIDIA_DRIVER_INIT_ERROR) {
			printErrorAndExit("NVIDIA driver error:" + err.Error())
		}
		printErrorAndExit(err.Error())
	}
	if err = docker.Wait(ctx); err != nil {
		printErrorAndExit("Failed to create docker container: " + err.Error())
	}

	output := strings.Split(strings.TrimRight(logger.String(), "\n"), "\n")
	if len(output) == 0 {
		printErrorAndExit("GPU not found")
	}
}

func printErrorAndExit(msg string) {
	_, _ = os.Stderr.WriteString(msg + "\n")
	os.Exit(1)
}
