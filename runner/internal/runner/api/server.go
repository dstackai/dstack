package api

import (
	"context"
	"errors"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/dstackai/dstack/runner/internal/api"
	"github.com/dstackai/dstack/runner/internal/executor"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
)

type Server struct {
	srv        *http.Server
	tempDir    string
	workingDir string

	shutdownCh   chan interface{} // server closes this chan on shutdown
	jobBarrierCh chan interface{} // only server listens on this chan
	pullDoneCh   chan interface{} // Closed then /api/pull gave everything
	wsDoneCh     chan interface{} // Closed then /logs_ws gave everything

	submitWaitDuration time.Duration
	logsWaitDuration   time.Duration

	executor  executor.Executor
	cancelRun context.CancelFunc

	version string
}

func NewServer(tempDir string, homeDir string, workingDir string, address string, version string) *Server {
	mux := http.NewServeMux()
	s := &Server{
		srv: &http.Server{
			Addr:    address,
			Handler: mux,
		},
		tempDir:    tempDir,
		workingDir: workingDir,

		shutdownCh:   make(chan interface{}),
		jobBarrierCh: make(chan interface{}),
		pullDoneCh:   make(chan interface{}),
		wsDoneCh:     make(chan interface{}),

		submitWaitDuration: 2 * time.Minute,
		logsWaitDuration:   30 * time.Second,

		executor: executor.NewRunExecutor(tempDir, homeDir, workingDir),

		version: version,
	}
	mux.HandleFunc("/api/healthcheck", api.JSONResponseHandler("GET", s.healthcheckGetHandler))
	mux.HandleFunc("/api/metrics", api.JSONResponseHandler("GET", s.metricsGetHandler))
	mux.HandleFunc("/api/submit", api.JSONResponseHandler("POST", s.submitPostHandler))
	mux.HandleFunc("/api/upload_code", api.JSONResponseHandler("POST", s.uploadCodePostHandler))
	mux.HandleFunc("/api/run", api.JSONResponseHandler("POST", s.runPostHandler))
	mux.HandleFunc("/api/pull", api.JSONResponseHandler("GET", s.pullGetHandler))
	mux.HandleFunc("/api/stop", api.JSONResponseHandler("POST", s.stopPostHandler))
	mux.HandleFunc("/logs_ws", api.JSONResponseHandler("GET", s.logsWsGetHandler))
	return s
}

func (s *Server) Run() error {
	signals := []os.Signal{os.Interrupt, syscall.SIGTERM, syscall.SIGKILL, syscall.SIGQUIT}
	signalCh := make(chan os.Signal, 1)

	go func() {
		if err := s.srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Error(context.TODO(), "Server failed", "err", err)
		}
	}()
	defer func() { _ = s.srv.Shutdown(context.TODO()) }()

	select {
	case <-s.jobBarrierCh: // job started
	case <-time.After(s.submitWaitDuration):
		log.Error(context.TODO(), "Job didn't start in time, shutting down")
		return gerrors.Newf("no job")
	}

	// todo timeout on code and run

	signal.Notify(signalCh, signals...)
	select {
	case <-signalCh:
		log.Error(context.TODO(), "Received interrupt signal, shutting down")
		s.stop()
	case <-s.jobBarrierCh:
		log.Info(context.TODO(), "Job finished, shutting down")
	}
	close(s.shutdownCh)
	signal.Reset(signals...)

	logsToWait := []struct {
		ch   <-chan interface{}
		name string
	}{
		{s.pullDoneCh, "/api/pull"},
		{s.wsDoneCh, "/logs_ws"},
	}
	waitLogsDone := time.After(s.logsWaitDuration)
loop:
	for _, ch := range logsToWait {
		select {
		case <-ch.ch:
			log.Info(context.TODO(), "Logs streaming finished", "endpoint", ch.name)
		case <-waitLogsDone:
			log.Error(context.TODO(), "Logs streaming didn't finish in time")
			break loop // break the loop, not the select
		}
	}

	return nil
}

func (s *Server) stop() {
	s.executor.Lock()
	defer s.executor.Unlock()
	if s.executor.GetRunnerState() == executor.ServeLogs {
		s.cancelRun()
	}
	s.executor.SetRunnerState(executor.WaitLogsFinished)
}
