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
	DockerKeepContainer() bool
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
		HTTPPort   int
		LogLevel   int
		Version    string
		DevChannel bool
		BinaryPath string
		TempDir    string
		HomeDir    string
		WorkingDir string
	}

	Docker struct {
		SSHPort                   int
		KeepContainer             bool
		ConcatinatedPublicSSHKeys string
		Privileged                bool
		PJRTDevice                string
	}
}

type MountPoint struct {
	Name string `json:"name"`
	Path string `json:"path"`
}

type VolumeInfo struct {
	Backend  string `json:"backend"`
	Name     string `json:"name"`
	VolumeId string `json:"volume_id"`
	InitFs   bool   `json:"init_fs"`
}

type TaskConfig struct {
	Username      string       `json:"username"`
	Password      string       `json:"password"`
	ImageName     string       `json:"image_name"`
	ContainerName string       `json:"container_name"`
	ContainerUser string       `json:"container_user"`
	ShmSize       int64        `json:"shm_size"`
	PublicKeys    []string     `json:"public_keys"`
	SshUser       string       `json:"ssh_user"`
	SshKey        string       `json:"ssh_key"`
	Mounts        []MountPoint `json:"mounts"`
	Volumes       []VolumeInfo `json:"volumes"`
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
