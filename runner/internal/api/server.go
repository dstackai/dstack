package api

import (
	"context"
	"errors"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"io"
	"net/http"
	"sync"
)

type Server struct {
	srv        *http.Server
	tempDir    string
	shutdownCh chan interface{} // todo how to use it?

	jobTerminatedCh chan interface{} // job terminated from the outside
	doneCh          chan interface{} // all logs have been collected

	stateMutex  sync.RWMutex
	serverState string // runner state machine
	// todo timeout waiting for the job or code or run
	jobCh  chan SubmitBody  // user submitted a job
	codeCh chan string      // user submitted a code
	runCh  chan interface{} // user triggered a run

	jobStateCh   chan string // executor sets job state
	jobLogsCh    chan []byte // executor writes job logs
	runnerLogsCh chan []byte // context logger writes runner logs

	historyMutex      sync.RWMutex
	timestamp         *MonotonicTimestamp
	jobStateHistory   []JobStateEvent
	jobLogsHistory    []LogEvent
	runnerLogsHistory []LogEvent
}

func NewServer(tempDir string, address string) *Server {
	mux := http.NewServeMux()
	s := &Server{
		srv: &http.Server{
			Addr:    address,
			Handler: mux,
		},
		tempDir:    tempDir,
		shutdownCh: make(chan interface{}),

		jobTerminatedCh: make(chan interface{}),
		doneCh:          make(chan interface{}),

		stateMutex:  sync.RWMutex{},
		serverState: WaitSubmit,
		jobCh:       make(chan SubmitBody),
		codeCh:      make(chan string),
		runCh:       make(chan interface{}),

		jobStateCh:   make(chan string),
		jobLogsCh:    make(chan []byte),
		runnerLogsCh: make(chan []byte),

		historyMutex:      sync.RWMutex{},
		timestamp:         NewMonotonicTimestamp(),
		jobStateHistory:   make([]JobStateEvent, 0),
		jobLogsHistory:    make([]LogEvent, 0),
		runnerLogsHistory: make([]LogEvent, 0),
	}
	setHandleFunc(mux, "GET", "/api/healthcheck", s.healthcheckGetHandler)
	setHandleFunc(mux, "POST", "/api/submit", s.submitPostHandler)
	setHandleFunc(mux, "POST", "/api/upload_code", s.uploadCodePostHandler)
	setHandleFunc(mux, "POST", "/api/run", s.runPostHandler)
	setHandleFunc(mux, "GET", "/api/pull", s.pullGetHandler)
	setHandleFunc(mux, "POST", "/api/stop", s.stopPostHandler)
	setHandleFunc(mux, "", "/logs_ws", s.logsWsGetHandler)
	return s
}

func (s *Server) Run() error {
	go s.collect()
	if err := s.srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		return gerrors.Wrap(err)
	}
	return nil
}

func (s *Server) Stop(ctx context.Context) error {
	close(s.shutdownCh)
	return gerrors.Wrap(s.srv.Shutdown(ctx))
}

func (s *Server) GetAdapter() *ServerAdapter {
	return &ServerAdapter{
		jobStateCh: s.jobStateCh,
		jobCh:      s.jobCh,
		codeCh:     s.codeCh,
		runCh:      s.runCh,
	}
}

func (s *Server) JobTerminated() <-chan interface{} {
	return s.jobTerminatedCh
}

func (s *Server) Done() <-chan interface{} {
	return s.doneCh
}

func (s *Server) RunnerLogsWriter() io.Writer {
	return NewLogsWriter(s.runnerLogsCh)
}

func (s *Server) JobLogsWriter() io.Writer {
	return NewLogsWriter(s.jobLogsCh)
}

func (s *Server) collect() {
	for {
		select {
		case state := <-s.jobStateCh:
			s.historyMutex.Lock()
			s.jobStateHistory = append(s.jobStateHistory, JobStateEvent{state, s.timestamp.Next()})
		case message := <-s.jobLogsCh:
			s.historyMutex.Lock()
			s.jobLogsHistory = append(s.jobLogsHistory, LogEvent{message, s.timestamp.Next()})
		case message := <-s.runnerLogsCh:
			s.historyMutex.Lock()
			s.runnerLogsHistory = append(s.runnerLogsHistory, LogEvent{message, s.timestamp.Next()})
		case <-s.shutdownCh:
			return
		}
		s.historyMutex.Unlock()
	}
}
