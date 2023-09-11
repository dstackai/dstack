package api

import (
	"encoding/json"
	"errors"
	"fmt"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/golang/gddo/httputil/header"
	"io"
	"net/http"
	"strings"
)

type malformedRequest struct {
	status int
	msg    string
}

func (mr *malformedRequest) Error() string {
	return mr.msg
}

func decodeJSONBody(w http.ResponseWriter, r *http.Request, dst interface{}, allowUnknown bool) error {
	// From https://www.alexedwards.net/blog/how-to-properly-parse-a-json-request-body
	if r.Header.Get("Content-Type") != "" {
		value, _ := header.ParseValueAndParams(r.Header, "Content-Type")
		if value != "application/json" {
			msg := "Content-Type header is not application/json"
			return &malformedRequest{status: http.StatusUnsupportedMediaType, msg: msg}
		}
	}

	r.Body = http.MaxBytesReader(w, r.Body, 1*1024*1024)

	dec := json.NewDecoder(r.Body)
	if !allowUnknown {
		dec.DisallowUnknownFields()
	}

	err := dec.Decode(&dst)
	if err != nil {
		var syntaxError *json.SyntaxError
		var unmarshalTypeError *json.UnmarshalTypeError

		switch {
		case errors.As(err, &syntaxError):
			msg := fmt.Sprintf("Request body contains badly-formed JSON (at position %d)", syntaxError.Offset)
			return &malformedRequest{status: http.StatusBadRequest, msg: msg}

		case errors.Is(err, io.ErrUnexpectedEOF):
			msg := fmt.Sprintf("Request body contains badly-formed JSON")
			return &malformedRequest{status: http.StatusBadRequest, msg: msg}

		case errors.As(err, &unmarshalTypeError):
			msg := fmt.Sprintf("Request body contains an invalid value for the %q field (at position %d)", unmarshalTypeError.Field, unmarshalTypeError.Offset)
			return &malformedRequest{status: http.StatusBadRequest, msg: msg}

		case strings.HasPrefix(err.Error(), "json: unknown field "):
			fieldName := strings.TrimPrefix(err.Error(), "json: unknown field ")
			msg := fmt.Sprintf("Request body contains unknown field %s", fieldName)
			return &malformedRequest{status: http.StatusBadRequest, msg: msg}

		case errors.Is(err, io.EOF):
			msg := "Request body must not be empty"
			return &malformedRequest{status: http.StatusBadRequest, msg: msg}

		case err.Error() == "http: request body too large":
			msg := "Request body must not be larger than 1MB"
			return &malformedRequest{status: http.StatusRequestEntityTooLarge, msg: msg}

		default:
			return err
		}
	}

	err = dec.Decode(&struct{}{})
	if !errors.Is(err, io.EOF) {
		msg := "Request body must only contain a single JSON object"
		return &malformedRequest{status: http.StatusBadRequest, msg: msg}
	}

	return nil
}

func writeJSONResponse(w http.ResponseWriter, statusCode int, payload interface{}) (int, string) {
	w.Header().Set("Content-Type", "application/json")
	bytes, err := json.Marshal(payload)
	if err != nil {
		return http.StatusInternalServerError, ""
	}
	return statusCode, string(bytes)
}

func setHandleFunc(mux *http.ServeMux, method string, path string, handler func(http.ResponseWriter, *http.Request) (int, string)) {
	mux.HandleFunc(path, func(w http.ResponseWriter, r *http.Request) {
		log.Debug(r.Context(), "", "method", r.Method, "endpoint", r.URL.Path)
		if method != "" && r.Method != method {
			http.Error(w, http.StatusText(http.StatusMethodNotAllowed), http.StatusMethodNotAllowed)
			return
		}
		status, body := handler(w, r)
		if status != 200 {
			http.Error(w, http.StatusText(status), status)
		} else {
			w.WriteHeader(status)
			_, _ = w.Write([]byte(body))
		}
	})
}
