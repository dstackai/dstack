package api

import (
	"encoding/base64"
	"encoding/json"
	"log"
	"net/http"

	"github.com/docker/docker/api/types/registry"
	"github.com/dstackai/dstack/runner/internal/api"
	"github.com/dstackai/dstack/runner/internal/shim"
)

func (s *ShimServer) healthcheckGetHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	return &HealthcheckResponse{
		Service: "dstack-shim",
	}, nil
}

func (s *ShimServer) registryAuthPostHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if s.state != shim.WaitRegistryAuth {
		return nil, &api.Error{Status: http.StatusConflict}
	}

	var body RegistryAuthBody
	if err := api.DecodeJSONBody(w, r, &body, true); err != nil {
		log.Println("Failed to decode submit body", "err", err)
		return nil, err
	}

	authConfig := registry.AuthConfig{
		Username: body.Username,
		Password: body.Password,
	}
	encodedConfig, err := json.Marshal(authConfig)
	if err != nil {
		log.Println("Failed to encode auth config", "err", err)
		return nil, err
	}
	s.registryAuth <- base64.URLEncoding.EncodeToString(encodedConfig)

	return nil, nil
}

func (s *ShimServer) pullGetHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	return &PullResponse{
		State: s.state,
	}, nil
}
