package api

import "github.com/dstackai/dstack/runner/internal/shim"

type HealthcheckResponse struct {
	Service string `json:"service"`
	Version string `json:"version"`
}

type TaskListResponse struct {
	IDs []string `json:"ids"`
}

type TaskInfoResponse struct {
	ID                 string             `json:"id"`
	Status             shim.TaskStatus    `json:"status"`
	TerminationReason  string             `json:"termination_reason"`
	TerminationMessage string             `json:"termination_message"`
	Ports              []shim.PortMapping `json:"ports"`
	// The following fields are for debugging only, server doesn't need them
	ContainerName string   `json:"container_name"`
	ContainerID   string   `json:"container_id"`
	GpuIDs        []string `json:"gpus_ids"`
}

type TaskSubmitRequest = shim.TaskConfig

type TaskTerminateRequest struct {
	TerminationReason  string `json:"termination_reason"`
	TerminationMessage string `json:"termination_message"`
	Timeout            uint   `json:"timeout"`
}
