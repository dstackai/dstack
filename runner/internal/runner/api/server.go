package api

import (
	"context"
	"errors"
	"net/http"
	_ "net/http/pprof"
	"sync"
	"time"

	"github.com/dstackai/dstack/runner/internal/common/api"
	"github.com/dstackai/dstack/runner/internal/common/log"
	"github.com/dstackai/dstack/runner/internal/runner/executor"
	"github.com/dstackai/dstack/runner/internal/runner/metrics"
)

type Server struct {
	srv *http.Server

	shutdownCh   chan interface{} // server closes this chan on shutdown
	jobBarrierCh chan interface{} // only server listens on this chan
	pullDoneCh   chan interface{} // Closed then /api/pull gave everything
	pullDoneOnce sync.Once
	wsDoneCh     chan interface{} // Closed then /logs_ws gave everything
	wsDoneOnce   sync.Once

	startWaitDuration time.Duration
	logsWaitDuration  time.Duration

	executor  executor.Executor
	cancelRun context.CancelFunc

	metricsCollector *metrics.MetricsCollector

	version string
}

func NewServer(ctx context.Context, address string, version string, ex executor.Executor) (*Server, error) {
	r := api.NewRouter()

	metricsCollector, err := metrics.NewMetricsCollector(ctx)
	if err != nil {
		log.Warning(ctx, "Metrics collector is not available", "err", err)
	}

	s := &Server{
		srv: &http.Server{
			Addr:    address,
			Handler: r,
		},

		shutdownCh:   make(chan interface{}),
		jobBarrierCh: make(chan interface{}),
		pullDoneCh:   make(chan interface{}),
		wsDoneCh:     make(chan interface{}),

		startWaitDuration: 5 * time.Minute,
		logsWaitDuration:  5 * time.Minute,

		executor: ex,

		metricsCollector: metricsCollector,

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

func (s *Server) Run(ctx context.Context) error {
	go func() {
		if err := s.srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Error(ctx, "Server failed", "err", err)
		}
	}()
	defer func() { _ = s.srv.Shutdown(ctx) }()

	select {
	case <-s.jobBarrierCh: // job started
	case <-time.After(s.startWaitDuration):
		log.Error(ctx, "Job didn't start in time, shutting down")
		return errors.New("no job submitted")
	case <-ctx.Done():
		log.Error(ctx, "Received interrupt signal, shutting down")
		return ctx.Err()
	}

	// todo timeout on code and run

	select {
	case <-s.jobBarrierCh:
		log.Info(ctx, "Job finished, shutting down")
	case <-ctx.Done():
		log.Error(ctx, "Received interrupt signal, shutting down")
		s.stop()
	}
	close(s.shutdownCh)

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
			log.Info(ctx, "Logs streaming finished", "endpoint", ch.name)
		case <-waitLogsDone:
			log.Error(ctx, "Logs streaming didn't finish in time")
			break loop // break the loop, not the select
		}
	}

	return nil
}

// closePullDone reports that /api/pull has served the final logs.
//
// More than one request may observe the WaitLogsFinished state: the state is set as soon as
// the job is asked to stop, while the server keeps serving until the executor returns, which
// may take arbitrarily long if the job leaves processes behind. Closing must be idempotent.
func (s *Server) closePullDone() {
	s.pullDoneOnce.Do(func() { close(s.pullDoneCh) })
}

// closeWsDone reports that a /logs_ws stream has sent the final logs.
//
// Nothing limits the number of concurrent connections, and each one is served by its own
// goroutine, so more than one may drain. Closing must be idempotent.
func (s *Server) closeWsDone() {
	s.wsDoneOnce.Do(func() { close(s.wsDoneCh) })
}

// stop asks the job to stop. The runner state is deliberately left alone: the executor sets
// WaitLogsFinished when it has actually finished, and that is what tells /api/pull the state
// it serves is final. Setting it here would mark a pull served while the job is still stopping
// as the final one, and the runner would exit without ever handing over the job's real state.
func (s *Server) stop() {
	s.executor.Lock()
	defer s.executor.Unlock()
	if s.executor.GetRunnerState() == executor.ServeLogs {
		s.cancelRun()
	}
}
