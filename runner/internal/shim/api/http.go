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
	if s.runner.GetState() != shim.Pending {
		return nil, &api.Error{Status: http.StatusConflict}
	}

	var body DockerTaskBody
	if err := api.DecodeJSONBody(w, r, &body, true); err != nil {
		log.Println("Failed to decode submit body", "err", err)
		return nil, err
	}

	go func(taskParams shim.DockerImageConfig) {
		err := s.runner.Run(context.TODO(), taskParams)
		if err != nil {
			fmt.Printf("failed Run %v", err)
		}
	}(body.TaskParams())

	return nil, nil
}

func (s *ShimServer) PullGetHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	return &PullResponse{
		State: string(s.runner.GetState()),
	}, nil
}

func (s *ShimServer) SubmitStopPostHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var body SubmitStopBody
	if err := api.DecodeJSONBody(w, r, &body, true); err != nil {
		log.Println("Failed to decode submit stop body", "err", err)
		return nil, err
	}

	s.runner.SubmitStop(body.Force)

	return &SubmitStopResponse{
		State: string(s.runner.GetState()),
	}, nil
}
