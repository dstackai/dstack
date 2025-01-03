package api

import (
	"context"
	"net/http"
	"sync"

	"github.com/dstackai/dstack/runner/internal/api"
	"github.com/dstackai/dstack/runner/internal/shim"
)

type TaskRunner interface {
	Submit(context.Context, shim.TaskConfig) error
	Run(ctx context.Context, taskID string) error
	Terminate(ctx context.Context, taskID string, timeout uint, reason string, message string) error
	Remove(ctx context.Context, taskID string) error

	Resources() shim.Resources
	TaskIDs() []string
	TaskInfo(taskID string) shim.TaskInfo

	GetState() (shim.RunnerStatus, shim.JobResult)
}

type ShimServer struct {
	HttpServer *http.Server
	mu         sync.RWMutex

	runner TaskRunner

	version string
}

func NewShimServer(address string, runner TaskRunner, version string) *ShimServer {
	r := api.NewRouter()
	s := &ShimServer{
		HttpServer: &http.Server{
			Addr:    address,
			Handler: r,
		},

		runner: runner,

		version: version,
	}

	// Stable API
	// The healthcheck endpoint should stay backward compatible, as it is used for negotiation
	r.AddHandler("GET", "/api/healthcheck", s.HealthcheckHandler)

	// Future API
	r.AddHandler("GET", "/api/tasks", s.TaskListHandler)
	r.AddHandler("GET", "/api/tasks/{id}", s.TaskInfoHandler)
	r.AddHandler("POST", "/api/tasks", s.TaskSubmitHandler)
	r.AddHandler("POST", "/api/tasks/{id}/terminate", s.TaskTerminateHandler)
	r.AddHandler("POST", "/api/tasks/{id}/remove", s.TaskRemoveHandler)

	// Legacy API
	r.AddHandler("POST", "/api/submit", s.LegacySubmitPostHandler)
	r.AddHandler("GET", "/api/pull", s.LegacyPullGetHandler)
	r.AddHandler("POST", "/api/stop", s.LegacyStopPostHandler)

	return s
}
