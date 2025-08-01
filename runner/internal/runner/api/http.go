package api

import (
	"context"
	"errors"
	"fmt"
	"io"
	"math"
	"mime"
	"mime/multipart"
	"net/http"
	"os"
	"path/filepath"
	"strconv"

	"github.com/dstackai/dstack/runner/internal/api"
	"github.com/dstackai/dstack/runner/internal/executor"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/metrics"
	"github.com/dstackai/dstack/runner/internal/schemas"
)

func (s *Server) healthcheckGetHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	return &schemas.HealthcheckResponse{
		Service: "dstack-runner",
		Version: s.version,
	}, nil
}

func (s *Server) metricsGetHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	metricsCollector, err := metrics.NewMetricsCollector()
	if err != nil {
		return nil, &api.Error{Status: http.StatusInternalServerError, Err: err}
	}
	metrics, err := metricsCollector.GetSystemMetrics()
	if err != nil {
		return nil, &api.Error{Status: http.StatusInternalServerError, Err: err}
	}
	return metrics, nil
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

// uploadArchivePostHandler may be called 0 or more times, and must be called after submitPostHandler
// and before uploadCodePostHandler
func (s *Server) uploadArchivePostHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.executor.Lock()
	defer s.executor.Unlock()
	if s.executor.GetRunnerState() != executor.WaitCode {
		return nil, &api.Error{Status: http.StatusConflict}
	}

	contentType := r.Header.Get("Content-Type")
	if contentType == "" {
		return nil, &api.Error{Status: http.StatusBadRequest, Msg: "missing content-type header"}
	}
	mediaType, params, err := mime.ParseMediaType(contentType)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	if mediaType != "multipart/form-data" {
		return nil, &api.Error{Status: http.StatusBadRequest, Msg: fmt.Sprintf("multipart/form-data expected, got %s", mediaType)}
	}
	boundary := params["boundary"]
	if boundary == "" {
		return nil, &api.Error{Status: http.StatusBadRequest, Msg: "missing boundary"}
	}

	formReader := multipart.NewReader(r.Body, boundary)
	part, err := formReader.NextPart()
	if errors.Is(err, io.EOF) {
		return nil, &api.Error{Status: http.StatusBadRequest, Msg: "empty form"}
	}
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	fieldName := part.FormName()
	if fieldName == "" {
		return nil, &api.Error{Status: http.StatusBadRequest, Msg: "missing field name"}
	}
	if fieldName != "archive" {
		return nil, &api.Error{Status: http.StatusBadRequest, Msg: fmt.Sprintf("unexpected field %s", fieldName)}
	}
	archiveId := part.FileName()
	if archiveId == "" {
		return nil, &api.Error{Status: http.StatusBadRequest, Msg: "missing file name"}
	}
	if err := s.executor.AddFileArchive(archiveId, part); err != nil {
		return nil, gerrors.Wrap(err)
	}
	if _, err := formReader.NextPart(); !errors.Is(err, io.EOF) {
		return nil, &api.Error{Status: http.StatusBadRequest, Msg: "extra form field(s)"}
	}

	return nil, nil
}

func (s *Server) uploadCodePostHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.executor.Lock()
	defer s.executor.Unlock()
	if s.executor.GetRunnerState() != executor.WaitCode {
		return nil, &api.Error{Status: http.StatusConflict}
	}

	r.Body = http.MaxBytesReader(w, r.Body, math.MaxInt64)
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
