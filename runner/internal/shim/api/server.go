package api

import (
	"context"
	"net"
	"net/http"
	"sync"

	"github.com/dstackai/dstack/runner/internal/api"
	"github.com/dstackai/dstack/runner/internal/shim"
	"github.com/dstackai/dstack/runner/internal/shim/dcgm"
)

type TaskRunner interface {
	Submit(context.Context, shim.TaskConfig) error
	Run(ctx context.Context, taskID string) error
	Terminate(ctx context.Context, taskID string, timeout uint, reason string, message string) error
	Remove(ctx context.Context, taskID string) error

	Resources(context.Context) shim.Resources
	TaskIDs() []string
	TaskInfo(taskID string) shim.TaskInfo
}

type ShimServer struct {
	HttpServer *http.Server
	mu         sync.RWMutex

	runner TaskRunner

	dcgmExporter *dcgm.DCGMExporter

	version string
}

func NewShimServer(ctx context.Context, address string, runner TaskRunner, dcgmExporter *dcgm.DCGMExporter, version string) *ShimServer {
	r := api.NewRouter()
	s := &ShimServer{
		HttpServer: &http.Server{
			Addr:        address,
			Handler:     r,
			BaseContext: func(l net.Listener) context.Context { return ctx },
		},

		runner: runner,

		dcgmExporter: dcgmExporter,

		version: version,
	}

	// The healthcheck endpoint should stay backward compatible, as it is used for negotiation
	r.AddHandler("GET", "/api/healthcheck", s.HealthcheckHandler)
	r.AddHandler("GET", "/api/tasks", s.TaskListHandler)
	r.AddHandler("GET", "/api/tasks/{id}", s.TaskInfoHandler)
	r.AddHandler("POST", "/api/tasks", s.TaskSubmitHandler)
	r.AddHandler("POST", "/api/tasks/{id}/terminate", s.TaskTerminateHandler)
	r.AddHandler("POST", "/api/tasks/{id}/remove", s.TaskRemoveHandler)
	r.HandleFunc("GET /metrics/tasks/{id}", s.TaskMetricsHandler)

	return s
}
