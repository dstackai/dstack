package api

import "github.com/dstackai/dstack/runner/internal/shim"

type TaskConfigBody = shim.TaskConfig

type StopBody struct {
	Force bool `json:"force"`
}

type HealthcheckResponse struct {
	Service string `json:"service"`
	Version string `json:"version"`
}

type PullResponse struct {
	State  string         `json:"state"`
	Result shim.JobResult `json:"result"`
}

type StopResponse struct {
	State string `json:"state"`
}
