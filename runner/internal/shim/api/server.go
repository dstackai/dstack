package api

import (
	"context"
	"errors"
	"net/http"
	"sync"
	"time"

	"github.com/dstackai/dstack/runner/internal/api"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/shim"
)

type ShimServer struct {
	srv *http.Server

	mu           sync.RWMutex
	registryAuth shim.ImagePullConfig
	state        string
}

func NewShimServer(address string, registryAuthRequired bool) *ShimServer {
	mux := http.NewServeMux()
	s := &ShimServer{
		srv: &http.Server{
			Addr:    address,
			Handler: mux,
		},

		state: shim.WaitRegistryAuth,
	}
	if registryAuthRequired {
		mux.HandleFunc("/api/registry_auth", api.JSONResponseHandler("POST", s.registryAuthPostHandler))
	}
	mux.HandleFunc("/api/healthcheck", api.JSONResponseHandler("GET", s.healthcheckGetHandler))
	mux.HandleFunc("/api/pull", api.JSONResponseHandler("GET", s.pullGetHandler))
	return s
}

func (s *ShimServer) RunDocker(ctx context.Context, params shim.DockerParameters) error {
	go func() {
		if err := s.srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			panic(err)
		}
	}()
	defer func() {
		shutdownCtx, cancelShutdown := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancelShutdown()
		_ = s.srv.Shutdown(shutdownCtx)
	}()
	return gerrors.Wrap(shim.RunDocker(ctx, params, s))
}

func (s *ShimServer) GetRegistryAuth() shim.ImagePullConfig {
	return s.registryAuth
}

func (s *ShimServer) SetState(state string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.state = state
}
