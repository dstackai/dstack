package api

import "github.com/dstackai/dstack/runner/internal/shim"

type RegistryAuthBody struct {
	Username  string `json:"username"`
	Password  string `json:"password"`
	ImageName string `json:"image_name"`
}

type HealthcheckResponse struct {
	Service string `json:"service"`
}

type PullResponse struct {
	State string `json:"state"`
}

func (ra RegistryAuthBody) MakeConfig() shim.ImagePullConfig {
	res := shim.ImagePullConfig{
		ImageName: ra.ImageName,
		Username:  ra.Username,
		Password:  ra.Password,
	}
	return res
}
