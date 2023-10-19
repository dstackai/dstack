package shim

import (
	"github.com/docker/docker/api/types/mount"
)

type APIAdapter interface {
	GetRegistryAuth() <-chan string
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
