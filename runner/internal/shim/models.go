package shim

import (
	"encoding/base64"
	"encoding/json"
	"log"

	"github.com/docker/docker/api/types/mount"
	"github.com/docker/docker/api/types/registry"
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
	Username       string               `json:"username"`
	Password       string               `json:"password"`
	ImageName      string               `json:"image_name"`
	Privileged     bool                 `json:"privileged"`
	ContainerName  string               `json:"container_name"`
	ContainerUser  string               `json:"container_user"`
	ShmSize        int64                `json:"shm_size"`
	PublicKeys     []string             `json:"public_keys"`
	SshUser        string               `json:"ssh_user"`
	SshKey         string               `json:"ssh_key"`
	VolumeMounts   []VolumeMountPoint   `json:"mounts"`
	Volumes        []VolumeInfo         `json:"volumes"`
	InstanceMounts []InstanceMountPoint `json:"instance_mounts"`
}

func (ra TaskConfig) EncodeRegistryAuth() (string, error) {
	if ra.Username == "" && ra.Password == "" {
		return "", nil
	}

	authConfig := registry.AuthConfig{
		Username: ra.Username,
		Password: ra.Password,
	}

	encodedConfig, err := json.Marshal(authConfig)
	if err != nil {
		log.Println("Failed to encode auth config", "err", err)
		return "", err
	}

	return base64.URLEncoding.EncodeToString(encodedConfig), nil
}
