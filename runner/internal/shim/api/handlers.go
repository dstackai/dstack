package api

import (
	"context"
	"errors"
	"net/http"

	"github.com/dstackai/dstack/runner/internal/api"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/shim"
	"github.com/dstackai/dstack/runner/internal/shim/dcgm"
)

func (s *ShimServer) HealthcheckHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	return &HealthcheckResponse{
		Service: "dstack-shim",
		Version: s.version,
	}, nil
}

func (s *ShimServer) InstanceHealthHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	ctx := r.Context()
	response := InstanceHealthResponse{}
	if s.dcgmWrapper != nil {
		if dcgmHealth, err := s.dcgmWrapper.GetHealth(); err != nil {
			log.Error(ctx, "failed to get health from DCGM", "err", err)
		} else {
			response.DCGM = &dcgmHealth
		}
	}

	return &response, nil
}

func (s *ShimServer) TaskListHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	tasks := s.runner.TaskList()
	return &TaskListResponse{tasks}, nil
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
	if req.ID == "" {
		return nil, &api.Error{Status: http.StatusBadRequest, Msg: "empty id"}
	}
	if req.Name == "" {
		return nil, &api.Error{Status: http.StatusBadRequest, Msg: "empty name"}
	}
	if req.ImageName == "" {
		return nil, &api.Error{Status: http.StatusBadRequest, Msg: "empty image_name"}
	}
	if req.ContainerUser == "" {
		req.ContainerUser = "root"
	}
	if req.NetworkMode == "" {
		req.NetworkMode = shim.NetworkModeHost
	}
	ctx := r.Context()
	taskConfig := shim.TaskConfig(req)
	if err := s.runner.Submit(ctx, taskConfig); err != nil {
		if errors.Is(err, shim.ErrRequest) {
			log.Info(ctx, "already submitted", "task", taskConfig.ID, "err", err)
			return nil, &api.Error{Status: http.StatusConflict, Err: err}
		}
		log.Error(ctx, "conflict", "task", taskConfig.ID, "err", err)
		return nil, &api.Error{Status: http.StatusInternalServerError, Err: err}
	}
	log.Info(ctx, "submitted", "task", taskConfig.ID)

	ctx = log.WithLogger(context.Background(), log.GetLogger(ctx))
	go func() {
		if err := s.runner.Run(ctx, taskConfig.ID); err != nil {
			log.Error(ctx, "failed to run", "task", taskConfig.ID, "err", err)
		}
	}()

	return s.runner.TaskInfo(taskConfig.ID), nil
}

func (s *ShimServer) TaskTerminateHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	ctx := r.Context()
	taskID := r.PathValue("id")
	var req TaskTerminateRequest
	if err := api.DecodeJSONBody(w, r, &req, true); err != nil {
		return nil, err
	}
	if err := s.runner.Terminate(ctx, taskID, req.Timeout, req.TerminationReason, req.TerminationMessage); err != nil {
		if errors.Is(err, shim.ErrNotFound) {
			log.Info(ctx, "not found", "task", taskID, "err", err)
			return nil, &api.Error{Status: http.StatusNotFound, Err: err}
		}
		if errors.Is(err, shim.ErrRequest) {
			log.Info(ctx, "conflict", "task", taskID, "err", err)
			return nil, &api.Error{Status: http.StatusConflict, Err: err}
		}
		log.Error(ctx, "failed to terminate", "task", taskID, "err", err)
		return nil, &api.Error{Status: http.StatusInternalServerError, Err: err}
	}
	log.Info(ctx, "terminated", "task", taskID)

	taskInfo := s.runner.TaskInfo(taskID)
	if taskInfo.ID == "" {
		return nil, &api.Error{Status: http.StatusNotFound}
	}
	return TaskInfoResponse(taskInfo), nil
}

func (s *ShimServer) TaskRemoveHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	ctx := r.Context()
	taskID := r.PathValue("id")
	if err := s.runner.Remove(ctx, taskID); err != nil {
		if errors.Is(err, shim.ErrNotFound) {
			log.Info(ctx, "not found", "task", taskID, "err", err)
			return nil, &api.Error{Status: http.StatusNotFound, Err: err}
		}
		if errors.Is(err, shim.ErrRequest) {
			log.Info(ctx, "not terminated", "task", taskID, "err", err)
			return nil, &api.Error{Status: http.StatusConflict, Err: err}
		}
		log.Error(ctx, "failed to remove", "task", taskID, "err", err)
		return nil, &api.Error{Status: http.StatusInternalServerError, Err: err}
	}
	log.Info(ctx, "removed", "task", taskID)
	return nil, nil
}

func (s *ShimServer) TaskMetricsHandler(w http.ResponseWriter, r *http.Request) {
	if s.dcgmExporter == nil {
		http.Error(w, "DCGM Exporter is not available", http.StatusNotFound)
		return
	}
	taskInfo := s.runner.TaskInfo(r.PathValue("id"))
	if taskInfo.ID == "" {
		http.Error(w, "Task not found", http.StatusNotFound)
		return
	}
	expfmtBody, err := s.dcgmExporter.Fetch(r.Context())
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}
	response := dcgm.FilterMetrics(expfmtBody, taskInfo.GpuIDs)
	_, _ = w.Write(response)
}
