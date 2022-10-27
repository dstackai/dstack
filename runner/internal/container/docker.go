package container

import (
	"context"
	"errors"
	"fmt"
	"io"
	"sync"
	"time"

	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/api/types/filters"
	"github.com/docker/docker/api/types/mount"
	docker "github.com/docker/docker/client"
	"github.com/docker/docker/pkg/stdcopy"
	"github.com/docker/go-connections/nat"
	"github.com/dstackai/dstackai/runner/internal/log"
	"github.com/sirupsen/logrus"
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

func (c *DockerContainer) Run(ctx context.Context) error {
	log.Trace(ctx, "Start pull image")
	err := c.PullImageIfAbsent(c.Image)
	if err != nil {
		log.Error(ctx, fmt.Sprintf("failed to download docker image: %s", err))
		return errors.New(fmt.Sprintf("failed to download docker image: %s", err))
	}
	log.Trace(ctx, "End pull image")

	log.Trace(ctx, fmt.Sprintf("Creating docker container for image: %s", c.Image))
	log.Trace(ctx, "container params: ", "mounts: ", c.Mounts)
	log.Trace(ctx, "Container command: ", "cmd: ", c.Commands)

	hostConfig := &container.HostConfig{
		NetworkMode:     "host",
		PortBindings:    c.BindingPorts,
		PublishAllPorts: true,
		ShmSize:         c.ShmSize * 1024 * 1024,
		Sysctls:         map[string]string{},
		Runtime:         c.runtime,
		Mounts:          c.Mounts,
	}

	resp, err := c.client.ContainerCreate(c.ctx,
		&container.Config{
			Image:        c.Image,
			Cmd:          c.Commands,
			Tty:          false,
			WorkingDir:   c.WorkDir,
			Env:          c.Env,
			ExposedPorts: c.ExposedPorts,
			Labels:       c.Labels,
		}, hostConfig, nil, nil, "")
	if err != nil {
		log.Error(ctx, fmt.Sprintf("failed to create container: %s", err))
		return errors.New(fmt.Sprintf("failed to create container: %s", err))
	}

	log.Trace(ctx, "Starting docker container")
	if err = c.client.ContainerStart(c.ctx, resp.ID, types.ContainerStartOptions{}); err != nil {
		return errors.New(fmt.Sprintf("failed to start container: %s", err))
	}

	log.Trace(ctx, "Sending docker logs to given buffers")
	out, err := c.client.ContainerLogs(c.ctx, resp.ID, types.ContainerLogsOptions{ShowStdout: true, ShowStderr: true, Follow: true})
	if err != nil {
		return errors.New(fmt.Sprintf("failed to get container logs: %s", err))
	}

	wg := new(sync.WaitGroup)
	wg.Add(1)
	go func() {
		_, err := stdcopy.StdCopy(c.logger, c.logger, out)
		if err != nil {
			log.Warning(c.ctx, "failed to stream container logs", "err", err)
		}
		wg.Done()
	}()

	log.Trace(ctx, "Waiting for docker container")
	statusCh, errCh := c.client.ContainerWait(c.ctx, resp.ID, container.WaitConditionNotRunning)
	select {
	case err := <-errCh:
		if err != nil && !errors.Is(err, context.Canceled) {
			return err
		} else {
			log.Debug(ctx, fmt.Sprintf("Container wait: %s", context.Canceled))
		}
	case status := <-statusCh:
		wg.Wait()
		c.ContainerCleanup(resp.ID)
		log.Trace(ctx, fmt.Sprintf("Container exited with exit code: %d\n", status.StatusCode))
		if status.StatusCode != 0 {
			return fmt.Errorf("container exited with exit code: %d", status.StatusCode)
		}
		return nil
	}

	select {
	case <-c.ctx.Done():
		wg.Wait()
		log.Error(ctx, fmt.Sprintf("Context got cancelled: %s", c.ctx.Err()))
		c.ContainerCleanup(resp.ID)
	}

	return nil
}

func (c *DockerContainer) ContainerCleanup(containerId string) {
	timeout := time.Second
	ctx, cancel := context.WithTimeout(context.Background(), timeout*2)
	defer cancel()

	log.Trace(c.ctx, fmt.Sprintf("%s: Executing container stop....", context.Canceled))
	err := c.client.ContainerStop(ctx, containerId, &timeout)
	if err != nil {
		log.Error(c.ctx, fmt.Sprintf("Error found on Container stop: %v", err))
	}

	log.Trace(c.ctx, fmt.Sprintf("%s: Executing container remove....\n", context.Canceled))
	err = c.client.ContainerRemove(ctx, containerId, types.ContainerRemoveOptions{Force: true})
	if err != nil {
		log.Error(c.ctx, fmt.Sprintf("Error found on Container remove: %v", err))
	}

	select {
	case <-ctx.Done():
		log.Trace(c.ctx, fmt.Sprintf("Container cleanup successful: %s", ctx.Err()))
	}
}

func (c *DockerContainer) PullImageIfAbsent(image string) error {
	if image == "" {
		return errors.New("given image value is empty")
	}

	summaries, err := c.client.ImageList(c.ctx, types.ImageListOptions{
		Filters: filters.NewArgs(filters.Arg("reference", image)),
	})
	if err != nil {
		return err
	}

	if len(summaries) == 0 {
		reader, err := c.client.ImagePull(c.ctx, image, types.ImagePullOptions{})
		if err != nil {
			return err
		}

		_, err = io.Copy(logrus.StandardLogger().Out, reader) // todo fix too much log output on download
		return err
	}

	return nil
}

// todo control logic like graceful stop

func (c *DockerContainer) Stop() {
	panic("implement me")
}

func (c *DockerContainer) Abort() {
	panic("implement me")
}

func (c *DockerContainer) Done() chan struct{} {
	panic("implement me")
}

func (c *DockerContainer) IsStopping() bool {
	panic("implement me")
}

func (c *DockerContainer) IsAborting() bool {
	panic("implement me")
}
