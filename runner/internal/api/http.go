package api

import (
	"errors"
	"github.com/dstackai/dstack/runner/internal/log"
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
	s.stateMutex.Lock()
	defer s.stateMutex.Unlock()
	if s.serverState != WaitSubmit {
		return http.StatusConflict, ""
	}

	var body SubmitBody
	if err := decodeJSONBody(w, r, &body, true); err != nil {
		// todo log
		var mr *malformedRequest
		if errors.As(err, &mr) {
			return mr.status, mr.msg
		} else {
			return http.StatusInternalServerError, ""
		}
	}
	// todo pass to executor

	s.serverState = WaitCode
	return 200, "ok"
}

func (s *Server) uploadCodePostHandler(w http.ResponseWriter, r *http.Request) (int, string) {
	s.stateMutex.Lock()
	defer s.stateMutex.Unlock()
	if s.serverState != WaitCode {
		return http.StatusConflict, ""
	}

	r.Body = http.MaxBytesReader(w, r.Body, 10*1024*1024)
	file, err := os.Create(filepath.Join(s.tempDir, "code"))
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

	s.serverState = WaitRun
	return 200, "ok"
}

func (s *Server) runPostHandler(w http.ResponseWriter, r *http.Request) (int, string) {
	s.stateMutex.Lock()
	defer s.stateMutex.Unlock()
	if s.serverState != WaitRun {
		return http.StatusConflict, ""
	}

	// todo add code path
	// todo pass job and secrets to executor

	s.serverState = ServeLogs
	return 200, "ok"
}

func (s *Server) pullGetHandler(w http.ResponseWriter, r *http.Request) (int, string) {
	s.historyMutex.RLock()
	defer s.historyMutex.RUnlock()
	timestamp := int64(0)
	if r.URL.Query().Has("timestamp") {
		var err error
		timestamp, err = strconv.ParseInt(r.URL.Query().Get("timestamp"), 10, 64)
		if err != nil {
			return http.StatusBadRequest, ""
		}
	}

	return writeJSONResponse(w, http.StatusOK, PullResponse{
		JobStates:   eventsAfter(s.jobStateHistory, timestamp),
		JobLogs:     eventsAfter(s.jobLogsHistory, timestamp),
		RunnerLogs:  eventsAfter(s.runnerLogsHistory, timestamp),
		LastUpdated: s.timestamp.GetLatest(),
	})
}

func (s *Server) stopPostHandler(w http.ResponseWriter, r *http.Request) (int, string) {
	s.stateMutex.RLock()
	defer s.stateMutex.RUnlock()
	if s.serverState != ServeLogs {
		return http.StatusConflict, ""
	}

	close(s.jobTerminatedCh)
	return 200, "ok"
}
