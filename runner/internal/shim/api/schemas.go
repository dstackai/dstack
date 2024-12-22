package api

import "github.com/dstackai/dstack/runner/internal/shim"

type SubmitBody struct {
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
