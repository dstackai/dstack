package docker

import (
	"github.com/docker/docker/api/types/mount"
	"github.com/docker/go-connections/nat"
)

type Spec struct {
	Image              string
	RegistryAuthBase64 string
	WorkDir            string
	Commands           []string
	Entrypoint         []string
	Env                []string
	Labels             map[string]string
	Mounts             []mount.Mount
	ExposedPorts       nat.PortSet
	BindingPorts       nat.PortMap
	ShmSize            int64
	LocalPortsRange    string
	Runtime            string
	AllowHostMode      bool
}
