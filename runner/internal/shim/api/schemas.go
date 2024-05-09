package api

import "github.com/dstackai/dstack/runner/internal/shim"

type TaskConfigBody struct {
	Username      string   `json:"username"`
	Password      string   `json:"password"`
	ImageName     string   `json:"image_name"`
	ContainerName string   `json:"container_name"`
	ShmSize       int64    `json:"shm_size"`
	PublicKeys    []string `json:"public_keys"`
	SshUser       string   `json:"ssh_user"`
	SshKey        string   `json:"ssh_key"`
}

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

func (ra TaskConfigBody) GetTaskConfig() shim.TaskConfig {
	res := shim.TaskConfig{
		ImageName:     ra.ImageName,
		Username:      ra.Username,
		Password:      ra.Password,
		ContainerName: ra.ContainerName,
		ShmSize:       ra.ShmSize,
		PublicKeys:    ra.PublicKeys,
		SshUser:       ra.SshUser,
		SshKey:        ra.SshKey,
	}
	return res
}
