package api

import (
	"context"
	"errors"
	"github.com/dstackai/dstack/runner/internal/executor"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/schemas"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
)

func (s *Server) healthcheckGetHandler(w http.ResponseWriter, r *http.Request) (int, string) {
	return 200, "ok"
}

func (s *Server) submitPostHandler(w http.ResponseWriter, r *http.Request) (int, string) {
	s.executor.Lock()
	defer s.executor.Unlock()
	if s.executor.GetRunnerState() != executor.WaitSubmit {
		return http.StatusConflict, ""
	}

	var body schemas.SubmitBody
	if err := decodeJSONBody(w, r, &body, true); err != nil {
		log.Error(r.Context(), "Failed to decode submit body", "err", err)
		var mr *malformedRequest
		if errors.As(err, &mr) {
			return mr.status, mr.msg
		} else {
			return http.StatusInternalServerError, ""
		}
	}
	// todo go-playground/validator

	s.executor.SetJob(body)
	s.jobBarrierCh <- nil // notify server that job submitted

	return 200, "ok"
}

func (s *Server) uploadCodePostHandler(w http.ResponseWriter, r *http.Request) (int, string) {
	s.executor.Lock()
	defer s.executor.Unlock()
	if s.executor.GetRunnerState() != executor.WaitCode {
		return http.StatusConflict, ""
	}

	r.Body = http.MaxBytesReader(w, r.Body, 10*1024*1024)
	codePath := filepath.Join(s.tempDir, "code") // todo random name?
	file, err := os.Create(codePath)
	if err != nil {
		log.Error(r.Context(), "Failed to create code file", "err", err)
		return http.StatusInternalServerError, ""
	}
	defer func() { _ = file.Close() }()
	if _, err = io.Copy(file, r.Body); err != nil {
		log.Error(r.Context(), "Failed to write code file", "err", err)
		if err.Error() == "http: request body too large" {
			return http.StatusRequestEntityTooLarge, ""
		} else {
			return http.StatusInternalServerError, ""
		}
	}

	s.executor.SetCodePath(codePath)
	return 200, "ok"
}

func (s *Server) runPostHandler(w http.ResponseWriter, r *http.Request) (int, string) {
	s.executor.Lock()
	defer s.executor.Unlock()
	if s.executor.GetRunnerState() != executor.WaitRun {
		return http.StatusConflict, ""
	}

	runCtx := context.Background()
	runCtx, s.cancelRun = context.WithCancel(runCtx)
	go func() {
		_ = s.executor.Run(runCtx) // todo handle error
		s.jobBarrierCh <- nil      // notify server that job finished
	}()
	s.executor.SetRunnerState(executor.ServeLogs)

	return 200, "ok"
}

func (s *Server) pullGetHandler(w http.ResponseWriter, r *http.Request) (int, string) {
	s.executor.RLock()
	defer s.executor.RUnlock()
	timestamp := int64(0)
	if r.URL.Query().Has("timestamp") {
		var err error
		timestamp, err = strconv.ParseInt(r.URL.Query().Get("timestamp"), 10, 64)
		if err != nil {
			return http.StatusBadRequest, ""
		}
	}

	//if noMoreLogs {  // todo
	//	defer func() { s.logsDoneCh <- nil }()
	//}
	return writeJSONResponse(w, http.StatusOK, s.executor.GetHistory(timestamp))
}

func (s *Server) stopPostHandler(w http.ResponseWriter, r *http.Request) (int, string) {
	s.stop()

	return 200, "ok"
}
