package shim

import (
	"context"
	"github.com/docker/docker/api/types/mount"
	docker "github.com/docker/docker/client"
)

type RunnerConfig interface {
	GetDockerCommands() []string
	GetDockerMount() (*mount.Mount, error)
	GetTempDir() string
}

type RunnerParameters struct {
	RunnerVersion    string // cli or env
	UseDev           bool   // cli
	RunnerBinaryPath string // cli or env

	TempDir    string
	HomeDir    string
	WorkingDir string

	HttpPort int // cli or env
	LogLevel int // cli	or env

	tempBinaryPath string
}

type DockerConfig interface {
	PullImage(context.Context, docker.APIClient) error
	CreateContainer(context.Context, docker.APIClient) (string, error)
	RunContainer(context.Context, docker.APIClient, string) error
	Cleanup(context.Context, docker.APIClient, string) error
}

type DockerParameters struct {
	Runner RunnerConfig

	ImageName string // cli or env
	WithAuth  bool   // cli

	PublicSSHKey string // cli or env
	OpenSSHPort  int

	RegistryAuthBase64 string
	KeepContainer      bool // cli

	DstackHome string // dstack home dir
}
