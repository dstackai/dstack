package shim

import (
	"github.com/docker/docker/api/types/mount"
)

type DockerParameters interface {
	DockerPrivileged() bool
	DockerShellCommands([]string) []string
	DockerMounts(string) ([]mount.Mount, error)
	DockerPorts() []int
	MakeRunnerDir() (string, error)
	DockerPJRTDevice() string
}

type CLIArgs struct {
	Shim struct {
		HTTPPort int
		HomeDir  string
	}

	Runner struct {
		HTTPPort    int
		LogLevel    int
		DownloadURL string
		BinaryPath  string
		TempDir     string
		HomeDir     string
		WorkingDir  string
	}

	Docker struct {
		SSHPort                   int
		ConcatinatedPublicSSHKeys string
		Privileged                bool
		PJRTDevice                string
	}
}

type VolumeMountPoint struct {
	Name string `json:"name"`
	Path string `json:"path"`
}

type InstanceMountPoint struct {
	InstancePath string `json:"instance_path"`
	Path         string `json:"path"`
}

type VolumeInfo struct {
	Backend  string `json:"backend"`
	Name     string `json:"name"`
	VolumeId string `json:"volume_id"`
	InitFs   bool   `json:"init_fs"`
}

type TaskConfig struct {
	ID               string               `json:"id"`
	Name             string               `json:"name"`
	RegistryUsername string               `json:"registry_username"`
	RegistryPassword string               `json:"registry_password"`
	ImageName        string               `json:"image_name"`
	ContainerUser    string               `json:"container_user"`
	Privileged       bool                 `json:"privileged"`
	ShmSize          int64                `json:"shm_size"`
	PublicKeys       []string             `json:"public_keys"`
	SshUser          string               `json:"ssh_user"`
	SshKey           string               `json:"ssh_key"`
	Volumes          []VolumeInfo         `json:"volumes"`
	VolumeMounts     []VolumeMountPoint   `json:"volume_mounts"`
	InstanceMounts   []InstanceMountPoint `json:"instance_mounts"`
}

// a surrogate ID used for tasks submitted via legacy API
const LegacyTaskID = "00000000-0000-0000-0000-000000000000"
