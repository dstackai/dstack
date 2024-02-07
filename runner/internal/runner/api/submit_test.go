//go:build !race

package api

import (
	"net/http/httptest"
	"strings"
	"testing"

	common "github.com/dstackai/dstack/runner/internal/api"
	"github.com/dstackai/dstack/runner/internal/shim"
	"github.com/dstackai/dstack/runner/internal/shim/api"
)

func TestSubmit(t *testing.T) {

	request := httptest.NewRequest("POST", "/api/submit", strings.NewReader("{\"image_name\":\"ubuntu\"}"))
	responseRecorder := httptest.NewRecorder()

	dummyRunner := DummyRunner{}
	dummyRunner.State = shim.Pending

	server := api.NewShimServer(":12340", &dummyRunner, "0.0.1.dev2")

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
