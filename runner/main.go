package main

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"io/ioutil"
	"math/bits"
	_ "net/http/pprof"
	"os"
	"os/signal"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/backend"
	_ "github.com/dstackai/dstack/runner/internal/backend/azure"
	_ "github.com/dstackai/dstack/runner/internal/backend/gcp"
	_ "github.com/dstackai/dstack/runner/internal/backend/local"
	_ "github.com/dstackai/dstack/runner/internal/backend/s3"
	"github.com/dstackai/dstack/runner/internal/common"
	"github.com/dstackai/dstack/runner/internal/container"
	"github.com/dstackai/dstack/runner/internal/executor"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/models"
	"github.com/dstackai/dstack/runner/internal/ports"
	"github.com/dstackai/dstack/runner/internal/stream"
	"github.com/sirupsen/logrus"
	"github.com/urfave/cli/v2"
	"gopkg.in/yaml.v3"
)

func main() {
	App()
}

func start(logLevel int, httpPort int, configDir string) {
	ctx := context.Background()
	//Load runner config
	config := new(executor.Config)
	thePathConfig := filepath.Join(configDir, consts.RUNNER_FILE_NAME)
	if _, err := os.Stat(thePathConfig); os.IsNotExist(err) {
		fmt.Println(err)
		return
	}
	theConfigFile, err := ioutil.ReadFile(thePathConfig)
	if err != nil {
		fmt.Println(err)
		return
	}
	if err = yaml.Unmarshal(theConfigFile, config); err != nil {
		fmt.Println(err)
		return
	}

	if _, err = os.Stat(filepath.Join(configDir, "logs", "runners")); err != nil {
		if err = os.MkdirAll(filepath.Join(configDir, "logs", "runners"), 0o777); err != nil {
			fmt.Println(err)
			return
		}
	}

	pathLogRunner := filepath.Join(configDir, "logs", "runners", fmt.Sprintf("%s.log", config.Id))
	log.L.Logger.SetLevel(logrus.Level(logLevel))
	fileLog, err := os.OpenFile(pathLogRunner, os.O_RDWR|os.O_CREATE|os.O_APPEND, 0o777)
	if err != nil {
		return
	}
	defer fileLog.Close()
	log.L.Logger.SetOutput(io.MultiWriter(os.Stdout, fileLog))

	logCtx := log.WithLogger(ctx, log.L)
	log.Info(logCtx, fmt.Sprintf("Log level: %v", log.L.Logger.GetLevel().String()))
	log.Info(logCtx, "RUNNER START...")

	common.CreateTMPDir()

	pathConfig := filepath.Join(configDir, consts.CONFIG_FILE_NAME)

	b, err := backend.New(logCtx, pathConfig)
	if err != nil {
		log.L.Error("[ERROR]", err)
		os.Exit(1)
	}
	if httpPort == 0 {
		httpPort, err = ports.GetFreePort()
		if err != nil {
			log.L.Error("[ERROR]", err)
			os.Exit(1)
		}
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

	ctxSig, cancel := signal.NotifyContext(logCtx, os.Interrupt, syscall.SIGTERM, syscall.SIGKILL, syscall.SIGQUIT)

	defer ex.Shutdown(context.Background())

	if err = ex.Init(ctxSig, configDir); err != nil {
		log.Error(logCtx, "Failed to init executor", "err", err)
		cancel()

	}
	// Also temporary logic during transition
	wg := sync.WaitGroup{}
	wg.Add(1)

	go func() {
		if err = ex.Run(ctxSig); err != nil {
			log.Error(logCtx, "dstack-runner ended with an error: ", "err", err)
		}
		wg.Done()
	}()
	wg.Wait()

	cancel()
	time.Sleep(1 * time.Second) // TODO: ugly hack. Need wait for buf cloudwatch
}

func check(configDir string) error {
	ctx := context.Background()
	config := new(executor.Config)
	thePathConfig := filepath.Join(configDir, consts.RUNNER_FILE_NAME)
	if _, err := os.Stat(thePathConfig); os.IsNotExist(err) {
		return cli.Exit("Failed to load config", 1)
	}
	theConfigFile, err := ioutil.ReadFile(thePathConfig)
	if err != nil {
		return cli.Exit("Unexpected error, please try to rerun", 1)
	}
	if err = yaml.Unmarshal(theConfigFile, config); err != nil {
		return cli.Exit("Config file is corrupted or does not exists", 1)
	}

	config.Resources = new(models.Resource)
	engine := container.NewEngine()
	if engine == nil {
		return cli.Exit("Docker is not installed", 1)
	}
	config.Resources.CPUs, config.Resources.Memory = engine.CPU(), engine.MemMiB()
	if engine.DockerRuntime() == consts.NVIDIA_RUNTIME {
		var logger bytes.Buffer
		docker, err := engine.Create(ctx,
			&container.Spec{
				Image:    consts.NVIDIA_CUDA_IMAGE,
				Commands: strings.Split(consts.NVIDIA_SMI_CMD, " "),
			},
			&logger)
		if err != nil {
			return cli.Exit("Failed to create docker container: "+err.Error(), 1)
		}
		err = docker.Run(ctx)
		if err != nil {
			if strings.Contains(err.Error(), consts.NVIDIA_DRIVER_INIT_ERROR) {
				return cli.Exit("NVIDIA driver error:"+err.Error(), 1)
			}
			return cli.Exit(err.Error(), 1)
		}
		if err = docker.Wait(ctx); err != nil {
			return cli.Exit("Failed to create docker container: "+err.Error(), 1)
		}

		output := strings.Split(strings.TrimRight(logger.String(), "\n"), "\n")
		var gpus []models.GPU
		for _, x := range output {
			regex := regexp.MustCompile(` *, *`)
			gpu := regex.Split(x, -1)
			memoryTotal := strings.Trim(strings.Split(gpu[1], "MiB")[0], " ")
			memoryMiB, err := strconv.ParseInt(memoryTotal, 10, bits.UintSize)
			if err != nil {
				return cli.Exit("GPU memory conversion to integer failed: "+err.Error(), 1)
			}
			gpus = append(gpus, models.GPU{
				Name:      gpu[0],
				MemoryMiB: int(memoryMiB),
			})
		}
		config.Resources.GPUs = gpus
	}
	theConfigFile, err = yaml.Marshal(config)
	if err != nil {
		return cli.Exit("Unexpected error, please try to rerun", 1)
	}
	err = ioutil.WriteFile(thePathConfig, theConfigFile, 0o644)
	if err != nil {
		return cli.Exit("Unexpected error, please try to rerun", 1)
	}

	return nil
}
