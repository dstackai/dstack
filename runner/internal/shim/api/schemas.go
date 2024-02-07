package api

import "github.com/dstackai/dstack/runner/internal/shim"

type DockerTaskBody struct {
	Username  string `json:"username"`
	Password  string `json:"password"`
	ImageName string `json:"image_name"`
}

type HealthcheckResponse struct {
	Service string `json:"service"`
	Version string `json:"version"`
}

type PullResponse struct {
	State string `json:"state"`
}

func (ra DockerTaskBody) TaskParams() shim.DockerImageConfig {
	res := shim.DockerImageConfig{
		ImageName: ra.ImageName,
		Username:  ra.Username,
		Password:  ra.Password,
	}
	return res
}
