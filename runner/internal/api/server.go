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
	srv      *http.Server
	tempDir  string
	shutdown chan interface{} // todo how to use it?

	jobTerminatedCh chan interface{}
	done            chan interface{}
	serverState     string
	stateMutex      sync.RWMutex

	jobStateCh   chan string
	jobLogsCh    chan []byte
	runnerLogsCh chan []byte

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
		tempDir:  tempDir,
		shutdown: make(chan interface{}),

		jobTerminatedCh: make(chan interface{}),
		done:            make(chan interface{}),
		serverState:     WaitSubmit,
		stateMutex:      sync.RWMutex{},

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
	close(s.shutdown)
	return gerrors.Wrap(s.srv.Shutdown(ctx))
}

func (s *Server) GetAdapter() *ServerAdapter {
	return NewServerAdapter(
		s.jobStateCh,
		// todo JobRun
	)
}

func (s *Server) JobTerminated() <-chan interface{} {
	return s.jobTerminatedCh
}

func (s *Server) Done() <-chan interface{} {
	return s.done
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
		case <-s.shutdown:
			return
		}
		s.historyMutex.Unlock()
	}
}
