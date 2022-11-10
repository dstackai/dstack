package container

import (
	"context"
	"io"

	"github.com/docker/docker/api/types/mount"
	docker "github.com/docker/docker/client"
	"github.com/docker/go-connections/nat"
)

// todo check copy-pasted code against modern docker API

type Mount struct {
	Host      string
	Container string
	Readonly  bool
}

type Container interface {
	Create(ctx context.Context, spec Spec, logger io.Writer) *DockerContainer
	Runtime() string
	CPUMemMiB() (int, uint64)
}

type Docker struct {
	ctx         context.Context
	client      *docker.Client
	runtime     string
	nCpu        int
	memTotalMiB uint64
}

type Spec struct {
	Image           string
	WorkDir         string
	Commands        []string
	Env             []string
	Labels          map[string]string
	Mounts          []mount.Mount
	ExposedPorts    nat.PortSet
	BindingPorts    nat.PortMap
	ShmSize         int64
	LocalPortsRange string
	Runtime         string
}

var _ = Container((*Docker)(nil))

func (d *Docker) Create(ctx context.Context, spec Spec, logger io.Writer) *DockerContainer {
	c := &DockerContainer{
		ctx:     ctx,
		Spec:    spec,
		logger:  logger,
		client:  d.client,
		runtime: d.runtime,
	}
	return c
}

type DockerContainer struct {
	ctx context.Context
	Spec
	logger io.Writer

	client  *docker.Client
	runtime string
}

func (d *Docker) Runtime() string {
	return d.runtime
}

func (d *Docker) CPUMemMiB() (int, uint64) {
	return d.nCpu, d.memTotalMiB
}
