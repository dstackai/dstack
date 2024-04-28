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
	GetState() (shim.RunnerStatus, shim.ContainerStatus, string, shim.JobResult)
	Stop(bool)
}

type ShimServer struct {
	HttpServer *http.Server
	mu         sync.RWMutex

	runner TaskRunner

	version string
}

func NewShimServer(address string, runner TaskRunner, version string) *ShimServer {
	mux := http.NewServeMux()
	s := &ShimServer{
		HttpServer: &http.Server{
			Addr:    address,
			Handler: mux,
		},

		runner: runner,

		version: version,
	}
	mux.HandleFunc("/api/submit", api.JSONResponseHandler("POST", s.SubmitPostHandler))
	mux.HandleFunc("/api/healthcheck", api.JSONResponseHandler("GET", s.HealthcheckGetHandler))
	mux.HandleFunc("/api/pull", api.JSONResponseHandler("GET", s.PullGetHandler))
	mux.HandleFunc("/api/stop", api.JSONResponseHandler("POST", s.StopPostHandler))
	return s
}
