package api

import (
	"context"
	"fmt"
	"log"
	"net/http"

	"github.com/dstackai/dstack/runner/internal/api"
	"github.com/dstackai/dstack/runner/internal/shim"
)

func (s *ShimServer) HealthcheckGetHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	return &HealthcheckResponse{
		Service: "dstack-shim",
		Version: s.version,
	}, nil
}

func (s *ShimServer) SubmitPostHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	state, _, _, _ := s.runner.GetState()
	if state != shim.Pending {
		return nil, &api.Error{Status: http.StatusConflict}
	}

	var body TaskConfigBody
	if err := api.DecodeJSONBody(w, r, &body, true); err != nil {
		log.Println("Failed to decode submit body", "err", err)
		return nil, err
	}

	go func(taskConfig shim.TaskConfig) {
		err := s.runner.Run(context.Background(), taskConfig)
		if err != nil {
			fmt.Printf("failed Run %v\n", err)
		}
	}(body.GetTaskConfig())

	return nil, nil
}

func (s *ShimServer) PullGetHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	state, containerStatus, executorError, jobResult := s.runner.GetState()

	return &PullResponse{
		State:         string(state),
		ExecutorError: executorError,
		ContainerName: containerStatus.ContainerName,
		Status:        containerStatus.Status,
		Running:       containerStatus.Running,
		OOMKilled:     containerStatus.OOMKilled,
		Dead:          containerStatus.Dead,
		ExitCode:      containerStatus.ExitCode,
		Error:         containerStatus.Error,
		Result:        jobResult,
	}, nil
}

func (s *ShimServer) StopPostHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	state, _, _, _ := s.runner.GetState()
	if state == shim.Pending {
		return &StopResponse{
			State: string(state),
		}, nil
	}

	var body StopBody
	if err := api.DecodeJSONBody(w, r, &body, true); err != nil {
		log.Println("Failed to decode submit stop body", "err", err)
		return nil, err
	}

	s.runner.Stop(body.Force)

	return &StopResponse{
		State: string(state),
	}, nil
}
