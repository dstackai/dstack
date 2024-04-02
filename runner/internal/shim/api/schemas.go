package api

import "github.com/dstackai/dstack/runner/internal/shim"

type DockerTaskBody struct {
	Username      string `json:"username"`
	Password      string `json:"password"`
	ImageName     string `json:"image_name"`
	ContainerName string `json:"container_name"`
	ShmSize       int64  `json:"shm_size"`
}

type StopBody struct {
	Force bool `json:"force"`
}

type HealthcheckResponse struct {
	Service string `json:"service"`
	Version string `json:"version"`
}

type PullResponse struct {
	State         string `json:"state"`
	ContainerName string `json:"container_name"`
	Status        string `json:"status"`
	Running       bool   `json:"running"`
	OOMKilled     bool   `json:"oom_killed"`
	Dead          bool   `json:"dead"`
	ExitCode      int    `json:"exit_code"`
	Error         string `json:"error"`
}

type StopResponse struct {
	State string `json:"state"`
}

func (ra DockerTaskBody) TaskParams() shim.DockerImageConfig {
	res := shim.DockerImageConfig{
		ImageName:     ra.ImageName,
		Username:      ra.Username,
		Password:      ra.Password,
		ContainerName: ra.ContainerName,
		ShmSize:       ra.ShmSize,
	}
	return res
}
