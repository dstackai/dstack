package api

import (
	"context"
	"net/http"
	"sync"

	"github.com/dstackai/dstack/runner/internal/api"
	"github.com/dstackai/dstack/runner/internal/shim"
)

type TaskRunner interface {
	Run(context.Context, shim.DockerImageConfig) error
	GetState() shim.RunnerStatus
}

type ShimServer struct {
	HttpServer *http.Server
	mu         sync.RWMutex

	runner TaskRunner
}

func NewShimServer(address string, runner TaskRunner) *ShimServer {
	mux := http.NewServeMux()
	s := &ShimServer{
		HttpServer: &http.Server{
			Addr:    address,
			Handler: mux,
		},

		runner: runner,
	}
	mux.HandleFunc("/api/submit", api.JSONResponseHandler("POST", s.SubmitPostHandler))
	mux.HandleFunc("/api/healthcheck", api.JSONResponseHandler("GET", s.HealthcheckGetHandler))
	mux.HandleFunc("/api/pull", api.JSONResponseHandler("GET", s.PullGetHandler))
	return s
}
