package api

import (
	"context"
	"errors"
	"fmt"
	"net/http"

	"github.com/dstackai/dstack/runner/internal/api"
	"github.com/dstackai/dstack/runner/internal/shim"
)

func (s *ShimServer) HealthcheckHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	return &HealthcheckResponse{
		Service: "dstack-shim",
		Version: s.version,
	}, nil
}

func (s *ShimServer) TaskListHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	return &TaskListResponse{IDs: s.runner.TaskIDs()}, nil
}

func (s *ShimServer) TaskInfoHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	taskInfo := s.runner.TaskInfo(r.PathValue("id"))
	if taskInfo.ID == "" {
		return nil, &api.Error{Status: http.StatusNotFound}
	}
	return TaskInfoResponse(taskInfo), nil
}

// TaskSubmitHandler submits AND runs a task
func (s *ShimServer) TaskSubmitHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	var req TaskSubmitRequest
	if err := api.DecodeJSONBody(w, r, &req, true); err != nil {
		return nil, err
	}
	taskConfig := shim.TaskConfig(req)
	if err := s.runner.Submit(r.Context(), taskConfig); err != nil {
		if errors.Is(err, shim.ErrRequest) {
			return nil, &api.Error{Status: http.StatusConflict, Err: err}
		}
		return nil, &api.Error{Status: http.StatusInternalServerError, Err: err}
	}
	go func(taskID string) {
		if err := s.runner.Run(context.Background(), taskID); err != nil {
			fmt.Printf("failed task %v", err)
		}
	}(taskConfig.ID)
	return s.runner.TaskInfo(taskConfig.ID), nil
}

func (s *ShimServer) TaskTerminateHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	taskID := r.PathValue("id")
	var req TaskTerminateRequest
	if err := api.DecodeJSONBody(w, r, &req, true); err != nil {
		return nil, err
	}
	if err := s.runner.Terminate(r.Context(), taskID, req.Timeout, req.TerminationReason, req.TerminationMessage); err != nil {
		if errors.Is(err, shim.ErrNotFound) {
			return nil, &api.Error{Status: http.StatusNotFound, Err: err}
		}
		if errors.Is(err, shim.ErrRequest) {
			return nil, &api.Error{Status: http.StatusConflict, Err: err}
		}
		return nil, &api.Error{Status: http.StatusInternalServerError, Err: err}
	}
	taskInfo := s.runner.TaskInfo(taskID)
	if taskInfo.ID == "" {
		return nil, &api.Error{Status: http.StatusNotFound}
	}
	return TaskInfoResponse(taskInfo), nil
}

func (s *ShimServer) TaskRemoveHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	if err := s.runner.Remove(r.Context(), r.PathValue("id")); err != nil {
		if errors.Is(err, shim.ErrNotFound) {
			return nil, &api.Error{Status: http.StatusNotFound, Err: err}
		}
		if errors.Is(err, shim.ErrRequest) {
			return nil, &api.Error{Status: http.StatusConflict, Err: err}
		}
		return nil, &api.Error{Status: http.StatusInternalServerError, Err: err}
	}
	return nil, nil
}
