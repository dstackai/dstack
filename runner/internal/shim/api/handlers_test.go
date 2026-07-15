package api

import (
	"context"
	"net/http/httptest"
	"strings"
	"testing"

	commonapi "github.com/dstackai/dstack/runner/internal/common/api"
	"github.com/dstackai/dstack/runner/internal/common/gpu"
	"github.com/dstackai/dstack/runner/internal/shim/host"
)

func TestHealthcheck(t *testing.T) {
	request := httptest.NewRequest("GET", "/api/healthcheck", nil)
	responseRecorder := httptest.NewRecorder()

	server := NewShimServer(context.Background(), ":12345", "0.0.1.dev2", NewDummyRunner(), nil, nil, nil, nil)

	f := commonapi.JSONResponseHandler(server.HealthcheckHandler)
	f(responseRecorder, request)

	if responseRecorder.Code != 200 {
		t.Errorf("Want status '%d', got '%d'", 200, responseRecorder.Code)
	}

	expected := "{\"service\":\"dstack-shim\",\"version\":\"0.0.1.dev2\"}"

	if strings.TrimSpace(responseRecorder.Body.String()) != expected {
		t.Errorf("Want '%s', got '%s'", expected, responseRecorder.Body.String())
	}
}

func TestHealthcheckWithGpus(t *testing.T) {
	request := httptest.NewRequest("GET", "/api/healthcheck", nil)
	responseRecorder := httptest.NewRecorder()

	runner := NewDummyRunner()
	runner.gpus = []host.GpuInfo{
		{Vendor: gpu.GpuVendorNvidia, Name: "T4", Vram: 16384, DriverVersion: "570.86.15"},
	}
	server := NewShimServer(context.Background(), ":12346", "0.0.1.dev2", runner, nil, nil, nil, nil)

	f := commonapi.JSONResponseHandler(server.HealthcheckHandler)
	f(responseRecorder, request)

	if responseRecorder.Code != 200 {
		t.Errorf("Want status '%d', got '%d'", 200, responseRecorder.Code)
	}

	expected := `{"service":"dstack-shim","version":"0.0.1.dev2","gpu_vendor":"nvidia","gpu_driver_version":"570.86.15"}`

	if strings.TrimSpace(responseRecorder.Body.String()) != expected {
		t.Errorf("Want '%s', got '%s'", expected, responseRecorder.Body.String())
	}
}

func TestTaskSubmit(t *testing.T) {
	server := NewShimServer(context.Background(), ":12340", "0.0.1.dev2", NewDummyRunner(), nil, nil, nil, nil)
	requestBody := `{
		"id": "dummy-id",
		"name": "dummy-name",
		"image_name": "ubuntu"
	}`

	request := httptest.NewRequest("POST", "/api/tasks", strings.NewReader(requestBody))
	responseRecorder := httptest.NewRecorder()
	firstSubmitPost := commonapi.JSONResponseHandler(server.TaskSubmitHandler)
	firstSubmitPost(responseRecorder, request)
	if responseRecorder.Code != 200 {
		t.Errorf("Want status '%d', got '%d'", 200, responseRecorder.Code)
	}

	request = httptest.NewRequest("POST", "/api/tasks", strings.NewReader(requestBody))
	responseRecorder = httptest.NewRecorder()
	secondSubmitPost := commonapi.JSONResponseHandler(server.TaskSubmitHandler)
	secondSubmitPost(responseRecorder, request)
	if responseRecorder.Code != 409 {
		t.Errorf("Want status '%d', got '%d'", 409, responseRecorder.Code)
	}
}
