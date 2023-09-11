package api

import (
	"context"
	"errors"
	"github.com/dstackai/dstack/runner/internal/executor"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

type Server struct {
	srv        *http.Server
	tempDir    string
	workingDir string

	shutdownCh   chan interface{} // server closes this chan on shutdown
	jobBarrierCh chan interface{} // only server listens on this chan
	logsDoneCh   chan interface{}

	submitWaitDuration time.Duration
	logsWaitDuration   time.Duration

	executor  *executor.Executor
	cancelRun context.CancelFunc
}

func NewServer(tempDir string, workingDir string, address string) *Server {
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

		submitWaitDuration: 2 * time.Minute,
		logsWaitDuration:   30 * time.Second,

		executor: executor.NewExecutor(tempDir, workingDir),
	}
	setHandleFunc(mux, "GET", "/api/healthcheck", s.healthcheckGetHandler)
	setHandleFunc(mux, "POST", "/api/submit", s.submitPostHandler)
	setHandleFunc(mux, "POST", "/api/upload_code", s.uploadCodePostHandler)
	setHandleFunc(mux, "POST", "/api/run", s.runPostHandler)
	setHandleFunc(mux, "GET", "/api/pull", s.pullGetHandler)
	setHandleFunc(mux, "POST", "/api/stop", s.stopPostHandler)
	setHandleFunc(mux, "GET", "/logs_ws", s.logsWsGetHandler)
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

	select {
	case <-s.logsDoneCh:
		log.Info(context.TODO(), "Logs streaming finished")
	case <-time.After(s.logsWaitDuration):
		log.Error(context.TODO(), "Logs streaming didn't finish in time")
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
