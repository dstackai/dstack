package api

import (
	"context"
	"errors"
	"net"
	"net/http"
	"reflect"
	"sync"

	"github.com/dstackai/dstack/runner/internal/api"
	"github.com/dstackai/dstack/runner/internal/shim"
	"github.com/dstackai/dstack/runner/internal/shim/components"
	"github.com/dstackai/dstack/runner/internal/shim/dcgm"
)

type TaskRunner interface {
	Submit(context.Context, shim.TaskConfig) error
	Run(ctx context.Context, taskID string) error
	Terminate(ctx context.Context, taskID string, timeout uint, reason string, message string) error
	Remove(ctx context.Context, taskID string) error

	Resources(context.Context) shim.Resources
	TaskList() []*shim.TaskListItem
	TaskInfo(taskID string) shim.TaskInfo
}

type ShimServer struct {
	httpServer *http.Server
	mu         sync.RWMutex

	bgJobsCtx    context.Context
	bgJobsCancel context.CancelFunc
	bgJobsGroup  *sync.WaitGroup

	runner TaskRunner

	dcgmExporter *dcgm.DCGMExporter
	dcgmWrapper  dcgm.DCGMWrapperInterface // interface with nil value normalized to plain nil

	runnerManager *components.RunnerManager

	version string
}

func NewShimServer(
	ctx context.Context, address string, version string,
	runner TaskRunner, dcgmExporter *dcgm.DCGMExporter, dcgmWrapper dcgm.DCGMWrapperInterface,
	runnerManager *components.RunnerManager,
) *ShimServer {
	bgJobsCtx, bgJobsCancel := context.WithCancel(ctx)
	if dcgmWrapper != nil && reflect.ValueOf(dcgmWrapper).IsNil() {
		dcgmWrapper = nil
	}
	r := api.NewRouter()
	s := &ShimServer{
		httpServer: &http.Server{
			Addr:        address,
			Handler:     r,
			BaseContext: func(l net.Listener) context.Context { return ctx },
		},

		bgJobsCtx:    bgJobsCtx,
		bgJobsCancel: bgJobsCancel,
		bgJobsGroup:  &sync.WaitGroup{},

		runner: runner,

		dcgmExporter: dcgmExporter,
		dcgmWrapper:  dcgmWrapper,

		runnerManager: runnerManager,

		version: version,
	}

	// The healthcheck endpoint should stay backward compatible, as it is used for negotiation
	r.AddHandler("GET", "/api/healthcheck", s.HealthcheckHandler)
	r.AddHandler("GET", "/api/instance/health", s.InstanceHealthHandler)
	r.AddHandler("GET", "/api/components", s.ComponentListHandler)
	r.AddHandler("POST", "/api/components/install", s.ComponentInstallHandler)
	r.AddHandler("GET", "/api/tasks", s.TaskListHandler)
	r.AddHandler("GET", "/api/tasks/{id}", s.TaskInfoHandler)
	r.AddHandler("POST", "/api/tasks", s.TaskSubmitHandler)
	r.AddHandler("POST", "/api/tasks/{id}/terminate", s.TaskTerminateHandler)
	r.AddHandler("POST", "/api/tasks/{id}/remove", s.TaskRemoveHandler)
	r.HandleFunc("GET /metrics/tasks/{id}", s.TaskMetricsHandler)

	return s
}

func (s *ShimServer) Serve() error {
	if err := s.httpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		return err
	}
	return nil
}

func (s *ShimServer) Shutdown(ctx context.Context) error {
	s.bgJobsCancel()
	err := s.httpServer.Shutdown(ctx)
	s.bgJobsGroup.Wait()
	return err
}
