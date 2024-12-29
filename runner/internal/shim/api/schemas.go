package api

import "github.com/dstackai/dstack/runner/internal/shim"

// Stable API

type HealthcheckResponse struct {
	Service string `json:"service"`
	Version string `json:"version"`
}

// Future API

type TaskListResponse struct {
	IDs []string `json:"ids"`
}

type TaskInfoResponse struct {
	ID                 string          `json:"id"`
	Status             shim.TaskStatus `json:"status"`
	TerminationReason  string          `json:"termination_reason"`
	TerminationMessage string          `json:"termination_message"`
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

// Legacy API

type LegacySubmitBody struct {
	Username       string                    `json:"username"`
	Password       string                    `json:"password"`
	ImageName      string                    `json:"image_name"`
	Privileged     bool                      `json:"privileged"`
	ContainerName  string                    `json:"container_name"`
	ContainerUser  string                    `json:"container_user"`
	ShmSize        int64                     `json:"shm_size"`
	PublicKeys     []string                  `json:"public_keys"`
	SshUser        string                    `json:"ssh_user"`
	SshKey         string                    `json:"ssh_key"`
	VolumeMounts   []shim.VolumeMountPoint   `json:"mounts"`
	Volumes        []shim.VolumeInfo         `json:"volumes"`
	InstanceMounts []shim.InstanceMountPoint `json:"instance_mounts"`
}

type LegacyPullResponse struct {
	State  string         `json:"state"`
	Result shim.JobResult `json:"result"`
}

type LegacyStopBody struct {
	Force bool `json:"force"`
}

type LegacyStopResponse struct {
	State string `json:"state"`
}
