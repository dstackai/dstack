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
	state, _ := s.runner.GetState()
	if state != shim.Pending {
		return nil, &api.Error{Status: http.StatusConflict}
	}

	var body SubmitBody
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
		GpuCount:         -1,
		ShmSize:          body.ShmSize,
		PublicKeys:       body.PublicKeys,
		SshUser:          body.SshUser,
		SshKey:           body.SshKey,
		Volumes:          body.Volumes,
		VolumeMounts:     body.VolumeMounts,
		InstanceMounts:   body.InstanceMounts,
	}
	go func(taskConfig shim.TaskConfig) {
		err := s.runner.Run(context.Background(), taskConfig)
		if err != nil {
			fmt.Printf("failed Run %v\n", err)
		}
	}(taskConfig)

	return nil, nil
}

func (s *ShimServer) PullGetHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	state, jobResult := s.runner.GetState()

	return &PullResponse{
		State:  string(state),
		Result: jobResult,
	}, nil
}

func (s *ShimServer) StopPostHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	state, _ := s.runner.GetState()
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
