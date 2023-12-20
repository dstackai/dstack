package shim

import (
	"encoding/base64"
	"encoding/json"
	"log"

	"github.com/docker/docker/api/types/mount"
	"github.com/docker/docker/api/types/registry"
)

type APIAdapter interface {
	GetRegistryAuth() ImagePullConfig
	SetState(string)
}

type DockerParameters interface {
	DockerImageName() string
	DockerKeepContainer() bool
	DockerShellCommands() []string
	DockerMounts() ([]mount.Mount, error)
	DockerPorts() []int
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
		SSHPort              int
		RegistryAuthRequired bool
		ImageName            string
		KeepContainer        bool
		PublicSSHKey         string
	}
}

type ImagePullConfig struct {
	Username  string
	Password  string
	ImageName string
}

func (ra ImagePullConfig) EncodeRegistryAuth() (string, error) {
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
