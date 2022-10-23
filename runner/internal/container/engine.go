package container

import (
	"context"
	"fmt"
	"io"
	"io/ioutil"
	"runtime"
	"strings"

	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/api/types/filters"
	docker "github.com/docker/docker/client"
	"github.com/docker/docker/pkg/stdcopy"
	"github.com/dstackai/dstackai/runner/consts"
	"github.com/dstackai/dstackai/runner/internal/gerrors"
	"github.com/dstackai/dstackai/runner/internal/log"
)

type Engine struct {
	client      docker.APIClient
	runtime     string
	nCpu        int
	memTotalMiB uint64
}

type Option interface {
	apply(engine *Engine)
}

type funcEngineOpt func(engine *Engine)

func (f funcEngineOpt) apply(engine *Engine) {
	f(engine)
}

func WithCustomClient(client docker.APIClient) Option {
	return funcEngineOpt(func(engine *Engine) {
		engine.client = client
	})
}

func NewEngine(opts ...Option) *Engine {
	ctx := context.Background()
	client, err := docker.NewClientWithOpts(docker.FromEnv, docker.WithAPIVersionNegotiation())
	if err != nil {
		log.Error(ctx, "Failed to create client", "err", err)
		return nil
	}
	info, err := client.Info(ctx)
	if err != nil {
		log.Error(ctx, "Failed fetch info about client", "err", err)
		return nil
	}
	var defaultRuntime = info.DefaultRuntime
	for name, _ := range info.Runtimes {
		if name == consts.NVIDIA_RUNTIME {
			defaultRuntime = name
		}
	}
	engine := &Engine{
		client:      client,
		runtime:     defaultRuntime,
		nCpu:        info.NCPU,
		memTotalMiB: BytesToMiB(info.MemTotal),
	}
	for _, opt := range opts {
		opt.apply(engine)
	}
	return engine
}

func (r *Engine) DockerRuntime() string {
	return r.runtime
}
func (r *Engine) CPU() int {
	return r.nCpu
}
func (r *Engine) MemMiB() uint64 {
	return r.memTotalMiB
}

type DockerRuntime struct {
	client      docker.APIClient
	containerID string
	logs        io.Writer
}

func (r *Engine) Create(ctx context.Context, spec *Spec, logs io.Writer) (*DockerRuntime, error) {
	log.Trace(ctx, "Start pull image")
	err := r.pullImageIfAbsent(ctx, spec.Image)
	if err != nil {
		log.Error(ctx, fmt.Sprintf("failed to download docker image: %s", err))
		return nil, gerrors.Newf("failed to download docker image: %s", err)
	}
	log.Trace(ctx, "End pull image")

	log.Trace(ctx, "Creating docker container", "image:", spec.Image)
	log.Trace(ctx, "container params: ", "mounts: ", spec.Mounts)
	log.Trace(ctx, "Container command: ", "cmd: ", spec.Commands)

	config := &container.Config{
		Image:        spec.Image,
		Cmd:          spec.Commands,
		Tty:          false,
		WorkingDir:   spec.WorkDir,
		Env:          spec.Env,
		ExposedPorts: spec.ExposedPorts,
		Labels:       spec.Labels,
	}
	var networkMode container.NetworkMode = "default"
	if supportNetworkModeHost() {
		networkMode = "host"
	}
	hostConfig := &container.HostConfig{
		NetworkMode:     networkMode,
		PortBindings:    spec.BindingPorts,
		PublishAllPorts: true,
		ShmSize:         spec.ShmSize * 1024 * 1024,
		Sysctls:         map[string]string{},
		Runtime:         r.runtime,
		Mounts:          spec.Mounts,
	}
	resp, err := r.client.ContainerCreate(ctx, config, hostConfig, nil, nil, "")
	if err != nil {
		log.Error(ctx, fmt.Sprintf("failed to create docker container: %s", err))
		return nil, gerrors.Wrap(err)
	}
	return &DockerRuntime{
		client:      r.client,
		containerID: resp.ID,
		logs:        logs,
	}, nil
}
func (r *DockerRuntime) Run(ctx context.Context) error {
	log.Trace(ctx, "Starting docker container")
	if err := r.client.ContainerStart(ctx, r.containerID, types.ContainerStartOptions{}); err != nil {
		log.Error(ctx, fmt.Sprintf("failed to start docker container: %s", err))
		return gerrors.Newf("failed to start container: %s", err)
	}

	if r.logs != nil {
		err := r.LogsWS(ctx)
		if err != nil {
			return gerrors.Wrap(err)
		}
	}
	return nil
}
func (r *DockerRuntime) Logs(ctx context.Context) error {
	opts := types.ContainerLogsOptions{
		ShowStdout: true,
		ShowStderr: true,
		Follow:     true,
	}
	logs, err := r.client.ContainerLogs(ctx, r.containerID, opts)
	if err != nil {
		log.Error(ctx, fmt.Sprintf("failed to stream container logs: %s", err))
		return gerrors.Newf("failed to stream container logs: %s", err)
	}
	go func() {
		//_, err = io.Copy(r.logs, logs)
		_, err = stdcopy.StdCopy(r.logs, r.logs, logs)
		if err != nil {
			log.Error(ctx, "failed to stream container logs", "err", gerrors.Wrap(err))
		}
		_ = logs.Close()
	}()
	return nil
}

func (r *DockerRuntime) LogsWS(ctx context.Context) error {
	logs, err := r.client.ContainerAttach(ctx, r.containerID, types.ContainerAttachOptions{
		Stream: true,
		Stdout: true,
		Stderr: true,
	})
	if err != nil {
		return gerrors.Wrap(err)
	}
	go func() {
		//_, err = io.Copy(r.logs, logs)
		_, err = stdcopy.StdCopy(r.logs, r.logs, logs.Reader)
		if err != nil {
			log.Error(ctx, "failed to stream container logs", "err", gerrors.Wrap(err))
		}
		logs.Close()
	}()
	return nil
}

func (r *DockerRuntime) Wait(ctx context.Context) error {
	wait, werr := r.client.ContainerWait(ctx, r.containerID, "")
	select {
	case <-wait:
	case err := <-werr:
		return gerrors.Wrap(err)
	}
	info, err := r.client.ContainerInspect(ctx, r.containerID)
	if err != nil {
		return gerrors.Wrap(err)
	}
	if info.State.ExitCode != 0 {
		return gerrors.Newf("container exited with exit code: %d", info.State.ExitCode)
	}
	removeOpts := types.ContainerRemoveOptions{
		Force: true,
	}

	err = r.client.ContainerRemove(ctx, r.containerID, removeOpts)
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (r *DockerRuntime) ForceStop(ctx context.Context) error {
	err := r.client.ContainerKill(ctx, r.containerID, "9")
	if err != nil {
		return gerrors.Wrap(err)
	}
	removeOpts := types.ContainerRemoveOptions{
		Force: true,
	}
	err = r.client.ContainerRemove(ctx, r.containerID, removeOpts)
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (r *DockerRuntime) Stop(ctx context.Context) error {
	err := r.client.ContainerKill(ctx, r.containerID, "SIGTERM")
	if err != nil {
		return gerrors.Wrap(err)
	}
	removeOpts := types.ContainerRemoveOptions{
		Force: true,
	}
	err = r.client.ContainerRemove(ctx, r.containerID, removeOpts)
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (r Engine) pullImageIfAbsent(ctx context.Context, image string) error {
	if image == "" {
		return gerrors.New("given image value is empty")
	}

	summaries, err := r.client.ImageList(ctx, types.ImageListOptions{
		Filters: filters.NewArgs(filters.Arg("reference", image)),
	})
	if err != nil {
		return gerrors.Wrap(err)
	}

	if len(summaries) != 0 {
		return nil
	}

	reader, err := r.client.ImagePull(ctx, image, types.ImagePullOptions{})
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = reader.Close() }()
	buf, err := ioutil.ReadAll(reader)
	if err != nil {
		return gerrors.Wrap(err)
	}
	log.Trace(ctx, "Image pull stdout", "stdout", string(buf))
	return nil
}

func ShellCommands(commands []string) []string {
	if len(commands) == 0 {
		return []string{}
	}
	arg := strings.Join(commands, " && ")
	shell := []string{
		"/bin/sh",
		"-c",
		arg,
	}
	return shell
}

func BytesToMiB(bytesCount int64) uint64 {
	var mib int64 = 1024 * 1024
	return uint64(bytesCount / mib)
}

func supportNetworkModeHost() bool {
	switch runtime.GOOS {
	case "linux":
		return true
	default:
		return false
	}
}
