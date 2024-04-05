package api

import (
	"context"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strconv"

	"github.com/dstackai/dstack/runner/internal/api"
	"github.com/dstackai/dstack/runner/internal/executor"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/schemas"
)

func (s *Server) healthcheckGetHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.executor.RLock()
	defer s.executor.RUnlock()
	return &schemas.HealthcheckResponse{
		Service: "dstack-runner",
		Version: s.version,
	}, nil
}

func (s *Server) submitPostHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.executor.Lock()
	defer s.executor.Unlock()
	state := s.executor.GetRunnerState()
	if state != executor.WaitSubmit {
		log.Warning(r.Context(), "Executor doesn't wait submit", "current_state", state)
		return nil, &api.Error{Status: http.StatusConflict}
	}

	var body schemas.SubmitBody
	if err := api.DecodeJSONBody(w, r, &body, true); err != nil {
		log.Error(r.Context(), "Failed to decode submit body", "err", err)
		return nil, err
	}
	// todo go-playground/validator

	s.executor.SetJob(body)
	s.jobBarrierCh <- nil // notify server that job submitted

	return nil, nil
}

func (s *Server) uploadCodePostHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.executor.Lock()
	defer s.executor.Unlock()
	if s.executor.GetRunnerState() != executor.WaitCode {
		return nil, &api.Error{Status: http.StatusConflict}
	}

	r.Body = http.MaxBytesReader(w, r.Body, 10*1024*1024)
	codePath := filepath.Join(s.tempDir, "code") // todo random name?
	file, err := os.Create(codePath)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	defer func() { _ = file.Close() }()
	if _, err = io.Copy(file, r.Body); err != nil {
		if err.Error() == "http: request body too large" {
			return nil, &api.Error{Status: http.StatusRequestEntityTooLarge}
		}
		return nil, gerrors.Wrap(err)
	}

	s.executor.SetCodePath(codePath)
	return nil, nil
}

func (s *Server) runPostHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.executor.Lock()
	defer s.executor.Unlock()
	if s.executor.GetRunnerState() != executor.WaitRun {
		return nil, &api.Error{Status: http.StatusConflict}
	}

	var runCtx context.Context
	runCtx, s.cancelRun = context.WithCancel(context.Background())
	go func() {
		_ = s.executor.Run(runCtx) // INFO: all errors are handled inside the Run()
		s.jobBarrierCh <- nil      // notify server that job finished
	}()
	s.executor.SetRunnerState(executor.ServeLogs)

	return nil, nil
}

func (s *Server) pullGetHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.executor.RLock()
	defer s.executor.RUnlock()
	timestamp := int64(0)
	if r.URL.Query().Has("timestamp") {
		var err error
		timestamp, err = strconv.ParseInt(r.URL.Query().Get("timestamp"), 10, 64)
		if err != nil {
			return nil, &api.Error{Status: http.StatusBadRequest}
		}
	}

	if s.executor.GetRunnerState() == executor.WaitLogsFinished {
		defer func() { close(s.pullDoneCh) }()
	}
	return s.executor.GetHistory(timestamp), nil
}

func (s *Server) stopPostHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.stop()

	return nil, nil
}
