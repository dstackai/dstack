package api

import (
	"context"
	"net/http/httptest"
	"strings"
	"testing"

	common "github.com/dstackai/dstack/runner/internal/api"
	"github.com/dstackai/dstack/runner/internal/shim"
	"github.com/dstackai/dstack/runner/internal/shim/api"
)

type DummyRunner struct {
	State     shim.RunnerStatus
	JobResult shim.JobResult
}

func (ds DummyRunner) GetState() (shim.RunnerStatus, shim.JobResult) {
	return ds.State, ds.JobResult
}

func (ds DummyRunner) Submit(context.Context, shim.TaskConfig) error {
	return nil
}

func (ds DummyRunner) Run(context.Context, string) error {
	return nil
}

func (ds DummyRunner) Terminate(context.Context, string, uint, string, string) error {
	return nil
}

func (ds DummyRunner) Remove(context.Context, string) error {
	return nil
}

func (ds DummyRunner) TaskIDs() []string {
	return []string{}
}

func (ds DummyRunner) TaskInfo(taskID string) shim.TaskInfo {
	return shim.TaskInfo{}
}

func (ds DummyRunner) Resources() shim.Resources {
	return shim.Resources{}
}

func TestHealthcheck(t *testing.T) {
	request := httptest.NewRequest("GET", "/api/healthcheck", nil)
	responseRecorder := httptest.NewRecorder()

	server := api.NewShimServer(":12345", DummyRunner{}, "0.0.1.dev2")

	f := common.JSONResponseHandler(server.HealthcheckHandler)
	f(responseRecorder, request)

	if responseRecorder.Code != 200 {
		t.Errorf("Want status '%d', got '%d'", 200, responseRecorder.Code)
	}

	expected := "{\"service\":\"dstack-shim\",\"version\":\"0.0.1.dev2\"}"

	if strings.TrimSpace(responseRecorder.Body.String()) != expected {
		t.Errorf("Want '%s', got '%s'", expected, responseRecorder.Body.String())
	}
}
