package shim

import (
	"encoding/base64"
	"encoding/json"
	"log"

	"github.com/docker/docker/api/types/mount"
	"github.com/docker/docker/api/types/registry"
)

type DockerParameters interface {
	DockerKeepContainer() bool
	DockerShellCommands() []string
	DockerMounts(string) ([]mount.Mount, error)
	DockerPorts() []int
	MakeRunnerDir() (string, error)
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
		SSHPort       int
		KeepContainer bool
		PublicSSHKey  string
	}
}

type DockerImageConfig struct {
	Username      string
	Password      string
	ImageName     string
	ContainerName string
	ShmSize       int64
}

func (ra DockerImageConfig) EncodeRegistryAuth() (string, error) {
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
