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
	State shim.RunnerStatus
}

func (ds DummyRunner) GetState() shim.RunnerStatus {
	return ds.State
}

func (ds DummyRunner) Run(context.Context, shim.DockerTaskConfig) error {
	return nil
}

func TestHealthcheck(t *testing.T) {

	request := httptest.NewRequest("GET", "/api/healthcheck", nil)
	responseRecorder := httptest.NewRecorder()

	server := api.NewShimServer(":12345", DummyRunner{})

	f := common.JSONResponseHandler("GET", server.HealthcheckGetHandler)
	f(responseRecorder, request)

	if responseRecorder.Code != 200 {
		t.Errorf("Want status '%d', got '%d'", 200, responseRecorder.Code)
	}

	expected := "{\"service\":\"dstack-shim\"}"

	if strings.TrimSpace(responseRecorder.Body.String()) != expected {
		t.Errorf("Want '%s', got '%s'", expected, responseRecorder.Body.String())
	}
}

func TestSubmit(t *testing.T) {

	request := httptest.NewRequest("POST", "/api/submit", strings.NewReader("{\"image_name\":\"ubuntu\"}"))
	responseRecorder := httptest.NewRecorder()

	dummyRunner := DummyRunner{}
	dummyRunner.State = shim.Pending

	server := api.NewShimServer(":12340", &dummyRunner)

	firstSubmitPost := common.JSONResponseHandler("POST", server.SubmitPostHandler)
	firstSubmitPost(responseRecorder, request)

	if responseRecorder.Code != 200 {
		t.Errorf("Want status '%d', got '%d'", 200, responseRecorder.Code)
	}

	t.Logf("%v", responseRecorder.Result())

	dummyRunner.State = shim.Pulling

	request = httptest.NewRequest("POST", "/api/submit", strings.NewReader("{\"image_name\":\"ubuntu\"}"))
	responseRecorder = httptest.NewRecorder()

	secondSubmitPost := common.JSONResponseHandler("POST", server.SubmitPostHandler)
	secondSubmitPost(responseRecorder, request)

	t.Logf("%v", responseRecorder.Result())

	if responseRecorder.Code != 409 {
		t.Errorf("Want status '%d', got '%d'", 409, responseRecorder.Code)
	}
}
