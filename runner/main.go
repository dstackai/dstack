package main

import (
	"context"
	"fmt"
	"github.com/dstackai/dstack/runner/internal/api"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/ports"
	"github.com/sirupsen/logrus"
	"io"
	_ "net/http/pprof"
	"os"
	"path/filepath"
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
	server := api.NewServer(tempDir, workingDir, fmt.Sprintf(":%d", httpPort))

	log.Trace(context.TODO(), "Starting API server", "port", httpPort)
	if err := server.Run(); err != nil {
		log.Error(context.TODO(), "Server failed", "err", err)
	}
}
