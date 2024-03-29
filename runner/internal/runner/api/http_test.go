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
	State           shim.RunnerStatus
	ContainerStatus shim.ContainerStatus
}

func (ds DummyRunner) GetState() (shim.RunnerStatus, shim.ContainerStatus, string) {
	return ds.State, ds.ContainerStatus, ""
}

func (ds DummyRunner) Run(context.Context, shim.DockerImageConfig) error {
	return nil
}

func (ds DummyRunner) Stop(force bool) {}

func TestHealthcheck(t *testing.T) {
	request := httptest.NewRequest("GET", "/api/healthcheck", nil)
	responseRecorder := httptest.NewRecorder()

	server := api.NewShimServer(":12345", DummyRunner{}, "0.0.1.dev2")

	f := common.JSONResponseHandler("GET", server.HealthcheckGetHandler)
	f(responseRecorder, request)

	if responseRecorder.Code != 200 {
		t.Errorf("Want status '%d', got '%d'", 200, responseRecorder.Code)
	}

	expected := "{\"service\":\"dstack-shim\",\"version\":\"0.0.1.dev2\"}"

	if strings.TrimSpace(responseRecorder.Body.String()) != expected {
		t.Errorf("Want '%s', got '%s'", expected, responseRecorder.Body.String())
	}
}
