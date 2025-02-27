package api

import (
	"context"
	"net/http/httptest"
	"strings"
	"testing"

	common "github.com/dstackai/dstack/runner/internal/api"
)

func TestHealthcheck(t *testing.T) {
	request := httptest.NewRequest("GET", "/api/healthcheck", nil)
	responseRecorder := httptest.NewRecorder()

	server := NewShimServer(context.Background(), ":12345", NewDummyRunner(), nil, "0.0.1.dev2")

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

func TestTaskSubmit(t *testing.T) {
	server := NewShimServer(context.Background(), ":12340", NewDummyRunner(), nil, "0.0.1.dev2")
	requestBody := `{
		"id": "dummy-id",
		"name": "dummy-name",
		"image_name": "ubuntu"
	}`

	request := httptest.NewRequest("POST", "/api/tasks", strings.NewReader(requestBody))
	responseRecorder := httptest.NewRecorder()
	firstSubmitPost := common.JSONResponseHandler(server.TaskSubmitHandler)
	firstSubmitPost(responseRecorder, request)
	if responseRecorder.Code != 200 {
		t.Errorf("Want status '%d', got '%d'", 200, responseRecorder.Code)
	}

	request = httptest.NewRequest("POST", "/api/tasks", strings.NewReader(requestBody))
	responseRecorder = httptest.NewRecorder()
	secondSubmitPost := common.JSONResponseHandler(server.TaskSubmitHandler)
	secondSubmitPost(responseRecorder, request)
	if responseRecorder.Code != 409 {
		t.Errorf("Want status '%d', got '%d'", 409, responseRecorder.Code)
	}
}
