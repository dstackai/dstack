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
	srv     *http.Server
	tempDir string

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

func NewServer(tempDir string, homeDir string, workingDir string, address string, sshPort int, version string) (*Server, error) {
	r := api.NewRouter()
	ex, err := executor.NewRunExecutor(tempDir, homeDir, workingDir, sshPort)
	if err != nil {
		return nil, err
	}
	s := &Server{
		srv: &http.Server{
			Addr:    address,
			Handler: r,
		},
		tempDir: tempDir,

		shutdownCh:   make(chan interface{}),
		jobBarrierCh: make(chan interface{}),
		pullDoneCh:   make(chan interface{}),
		wsDoneCh:     make(chan interface{}),

		submitWaitDuration: 5 * time.Minute,
		logsWaitDuration:   5 * time.Minute,

		executor: ex,

		version: version,
	}
	r.AddHandler("GET", "/api/healthcheck", s.healthcheckGetHandler)
	r.AddHandler("GET", "/api/metrics", s.metricsGetHandler)
	r.AddHandler("POST", "/api/submit", s.submitPostHandler)
	r.AddHandler("POST", "/api/upload_archive", s.uploadArchivePostHandler)
	r.AddHandler("POST", "/api/upload_code", s.uploadCodePostHandler)
	r.AddHandler("POST", "/api/run", s.runPostHandler)
	r.AddHandler("GET", "/api/pull", s.pullGetHandler)
	r.AddHandler("POST", "/api/stop", s.stopPostHandler)
	r.AddHandler("GET", "/logs_ws", s.logsWsGetHandler)
	return s, nil
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
