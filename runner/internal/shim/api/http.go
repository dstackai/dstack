package api

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"

	"github.com/dstackai/dstack/runner/internal/api"
	"github.com/dstackai/dstack/runner/internal/shim"
)

// Stable API

func (s *ShimServer) HealthcheckHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	return &HealthcheckResponse{
		Service: "dstack-shim",
		Version: s.version,
	}, nil
}

// Future API

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

// Legacy API

func (s *ShimServer) LegacySubmitPostHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	state, _ := s.runner.GetState()
	if state != shim.Pending {
		return nil, &api.Error{Status: http.StatusConflict}
	}

	var body LegacySubmitBody
	if err := api.DecodeJSONBody(w, r, &body, true); err != nil {
		log.Println("Failed to decode submit body", "err", err)
		return nil, err
	}

	taskConfig := shim.TaskConfig{
		ID:               shim.LegacyTaskID,
		Name:             body.ContainerName,
		RegistryUsername: body.Username,
		RegistryPassword: body.Password,
		ImageName:        body.ImageName,
		ContainerUser:    body.ContainerUser,
		Privileged:       body.Privileged,
		GPU:              -1,
		ShmSize:          body.ShmSize,
		Volumes:          body.Volumes,
		VolumeMounts:     body.VolumeMounts,
		InstanceMounts:   body.InstanceMounts,
		HostSshUser:      body.SshUser,
		HostSshKeys:      []string{body.SshKey},
		ContainerSshKeys: body.PublicKeys,
	}
	go func(taskConfig shim.TaskConfig) {
		if err := s.runner.Submit(context.Background(), taskConfig); err != nil {
			fmt.Printf("failed Submit %v", err)
		}
		if err := s.runner.Run(context.Background(), taskConfig.ID); err != nil {
			fmt.Printf("failed Run %v", err)
		}
	}(taskConfig)

	return nil, nil
}

func (s *ShimServer) LegacyPullGetHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	state, jobResult := s.runner.GetState()

	return &LegacyPullResponse{
		State:  string(state),
		Result: jobResult,
	}, nil
}

func (s *ShimServer) LegacyStopPostHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	state, _ := s.runner.GetState()
	if state == shim.Pending {
		return &LegacyStopResponse{
			State: string(state),
		}, nil
	}

	var body LegacyStopBody
	if err := api.DecodeJSONBody(w, r, &body, true); err != nil {
		log.Println("Failed to decode submit stop body", "err", err)
		return nil, err
	}

	var timeout uint
	if body.Force {
		timeout = 0
	} else {
		timeout = 10 // Docker default value
	}
	if err := s.runner.Terminate(r.Context(), shim.LegacyTaskID, timeout, "", ""); err != nil {
		log.Println("Failed to terminate", "err", err)
	}

	state, _ = s.runner.GetState()
	return &LegacyStopResponse{
		State: string(state),
	}, nil
}
