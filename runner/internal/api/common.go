package api

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"

	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/golang/gddo/httputil/header"
)

type Error struct {
	Status int
	Err    error
	Msg    string
}

func (e *Error) Error() string {
	if e.Msg != "" {
		return e.Msg
	}
	if e.Err != nil {
		return e.Err.Error()
	}
	return http.StatusText(e.Status)
}

type Router struct {
	*http.ServeMux
}

func (r *Router) AddHandler(method string, pattern string, handler func(http.ResponseWriter, *http.Request) (interface{}, error)) {
	r.HandleFunc(fmt.Sprintf("%s %s", method, pattern), JSONResponseHandler(handler))
}

func NewRouter() Router {
	return Router{http.NewServeMux()}
}

func DecodeJSONBody(w http.ResponseWriter, r *http.Request, dst interface{}, allowUnknown bool) error {
	// From https://www.alexedwards.net/blog/how-to-properly-parse-a-json-request-body
	if r.Header.Get("Content-Type") != "" {
		value, _ := header.ParseValueAndParams(r.Header, "Content-Type")
		msg := "Content-Type header is not application/json"
		if value != "application/json" {
			return &Error{Status: http.StatusUnsupportedMediaType, Msg: msg}
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
			return &Error{Status: http.StatusBadRequest, Msg: msg}

		case errors.Is(err, io.ErrUnexpectedEOF):
			msg := "Request body contains badly-formed JSON"
			return &Error{Status: http.StatusBadRequest, Msg: msg}

		case errors.As(err, &unmarshalTypeError):
			msg := fmt.Sprintf("Request body contains an invalid value for the %q field (at position %d)", unmarshalTypeError.Field, unmarshalTypeError.Offset)
			return &Error{Status: http.StatusBadRequest, Msg: msg}

		case strings.HasPrefix(err.Error(), "json: unknown field "):
			fieldName := strings.TrimPrefix(err.Error(), "json: unknown field ")
			msg := fmt.Sprintf("Request body contains unknown field %s", fieldName)
			return &Error{Status: http.StatusBadRequest, Msg: msg}

		case errors.Is(err, io.EOF):
			msg := "Request body must not be empty"
			return &Error{Status: http.StatusBadRequest, Msg: msg}

		case err.Error() == "http: request body too large":
			msg := "Request body must not be larger than 1MB"
			return &Error{Status: http.StatusRequestEntityTooLarge, Msg: msg}

		default:
			return err
		}
	}

	err = dec.Decode(&struct{}{})
	if !errors.Is(err, io.EOF) {
		msg := "Request body must only contain a single JSON object"
		return &Error{Status: http.StatusBadRequest, Msg: msg}
	}

	return nil
}

func JSONResponseHandler(handler func(http.ResponseWriter, *http.Request) (interface{}, error)) func(http.ResponseWriter, *http.Request) {
	return func(w http.ResponseWriter, r *http.Request) {
		status := 200
		errMsg := ""
		var apiErr *Error

		body, err := handler(w, r)
		if err != nil {
			if errors.As(err, &apiErr) {
				status = apiErr.Status
				errMsg = apiErr.Error()
				log.Warning(r.Context(), "API error", "err", errMsg, "status", status)
			} else {
				status = http.StatusInternalServerError
				log.Error(r.Context(), "Unexpected API error", "err", err, "status", status)
			}
		}

		if status != 500 && body != nil {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(status)
			_ = json.NewEncoder(w).Encode(body)
		} else {
			http.Error(w, errMsg, status)
		}

		log.Debug(r.Context(), "", "method", r.Method, "endpoint", r.URL.Path, "status", status)
	}
}
