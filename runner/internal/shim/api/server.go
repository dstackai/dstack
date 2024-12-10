package api

import (
	"context"
	"net/http"
	"sync"

	"github.com/dstackai/dstack/runner/internal/api"
	"github.com/dstackai/dstack/runner/internal/shim"
)

type TaskRunner interface {
	Run(context.Context, shim.TaskConfig) error
	GetState() (shim.RunnerStatus, shim.JobResult)
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
	// The healthcheck endpoint should stay backward compatible, as it is used for negotiation
	mux.HandleFunc("/api/healthcheck", api.JSONResponseHandler("GET", s.HealthcheckGetHandler))
	// The following endpoints constitute a so-called legacy API, where shim has one global state
	// and is able to process only one task at a time
	// NOTE: as of 2024-12-10, there is _only_ legacy API, but the "legacy" label is used to
	// distinguish the "old" API from the upcoming new one
	mux.HandleFunc("/api/submit", api.JSONResponseHandler("POST", s.SubmitPostHandler))
	mux.HandleFunc("/api/pull", api.JSONResponseHandler("GET", s.PullGetHandler))
	mux.HandleFunc("/api/stop", api.JSONResponseHandler("POST", s.StopPostHandler))
	return s
}
