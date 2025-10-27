package main

import (
	"context"
	"fmt"
	"io"
	_ "net/http/pprof"
	"os"
	"path/filepath"

	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/runner/api"
	"github.com/sirupsen/logrus"
)

func main() {
	App()
}

func start(tempDir string, homeDir string, httpPort int, sshPort int, logLevel int, version string) error {
	if err := os.MkdirAll(tempDir, 0o755); err != nil {
		return fmt.Errorf("create temp directory: %w", err)
	}

	defaultLogFile, err := log.CreateAppendFile(filepath.Join(tempDir, consts.RunnerDefaultLogFileName))
	if err != nil {
		return fmt.Errorf("create default log file: %w", err)
	}
	defer func() {
		err = defaultLogFile.Close()
		if err != nil {
			log.Error(context.TODO(), "Failed to close default log file", "err", err)
		}
	}()

	log.DefaultEntry.Logger.SetOutput(io.MultiWriter(os.Stdout, defaultLogFile))
	log.DefaultEntry.Logger.SetLevel(logrus.Level(logLevel))

	server, err := api.NewServer(tempDir, homeDir, fmt.Sprintf(":%d", httpPort), sshPort, version)
	if err != nil {
		return fmt.Errorf("create server: %w", err)
	}

	log.Trace(context.TODO(), "Starting API server", "port", httpPort)
	if err := server.Run(); err != nil {
		return fmt.Errorf("server failed: %w", err)
	}

	return nil
}
