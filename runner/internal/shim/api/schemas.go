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
	State         string         `json:"state"`
	ExecutorError string         `json:"executor_error"`
	ContainerName string         `json:"container_name"`
	Status        string         `json:"status"`
	Running       bool           `json:"running"`
	OOMKilled     bool           `json:"oom_killed"`
	Dead          bool           `json:"dead"`
	ExitCode      int            `json:"exit_code"`
	Error         string         `json:"error"`
	Result        shim.JobResult `json:"result"`
}

type StopResponse struct {
	State string `json:"state"`
}
