package shim

import (
	"github.com/docker/docker/api/types/mount"
)

type DockerParameters interface {
	DockerPrivileged() bool
	DockerShellCommands([]string) []string
	DockerMounts(string) ([]mount.Mount, error)
	DockerPorts() []int
	MakeRunnerDir(name string) (string, error)
	DockerPJRTDevice() string
}

type CLIArgs struct {
	Shim struct {
		HTTPPort int
		HomeDir  string
		LogLevel int
	}

	Runner struct {
		HTTPPort    int
		DownloadURL string
		BinaryPath  string
		LogLevel    int
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
	Backend    string `json:"backend"`
	Name       string `json:"name"`
	VolumeId   string `json:"volume_id"`
	InitFs     bool   `json:"init_fs"`
	DeviceName string `json:"device_name"`
}

type TaskConfig struct {
	ID               string               `json:"id"`
	Name             string               `json:"name"`
	RegistryUsername string               `json:"registry_username"`
	RegistryPassword string               `json:"registry_password"`
	ImageName        string               `json:"image_name"`
	ContainerUser    string               `json:"container_user"`
	Privileged       bool                 `json:"privileged"`
	GPU              int                  `json:"gpu"`      // -1 = all available, even if zero; 0 = zero, ...
	CPU              float64              `json:"cpu"`      // 0.0 = all available; 0.5 = a half of CPU, ...
	Memory           int64                `json:"memory"`   // bytes; 0 = all avaliable
	ShmSize          int64                `json:"shm_size"` // bytes; 0 = default (64MiB)
	Volumes          []VolumeInfo         `json:"volumes"`
	VolumeMounts     []VolumeMountPoint   `json:"volume_mounts"`
	InstanceMounts   []InstanceMountPoint `json:"instance_mounts"`
	HostSshUser      string               `json:"host_ssh_user"`
	HostSshKeys      []string             `json:"host_ssh_keys"`
	// TODO: submit keys to runner, not to shim
	ContainerSshKeys []string `json:"container_ssh_keys"`
}

type TaskInfo struct {
	ID                 string
	Status             TaskStatus
	TerminationReason  string
	TerminationMessage string
	ContainerName      string
	ContainerID        string
	GpuIDs             []string
}
