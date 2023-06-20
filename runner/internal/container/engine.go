package container

import (
	"context"
	"fmt"
	"io"
	"io/ioutil"
	"os/exec"
	"runtime"
	"strings"

	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/api/types/filters"
	docker "github.com/docker/docker/client"
	"github.com/docker/docker/pkg/stdcopy"
	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
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

type ContainerExitedError struct {
	ExitCode int
}

func (e ContainerExitedError) Error() string {
	return fmt.Sprintf("container exited with non-zero exit code: %d", e.ExitCode)
}

//nolint:all
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
	for name := range info.Runtimes {
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

func (r *Engine) DockerClient() docker.APIClient {
	return r.client
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
	err := r.pullImageIfAbsent(ctx, spec.Image, spec.RegistryAuthBase64)
	if err != nil {
		log.Error(ctx, fmt.Sprintf("failed to download docker image: %s", err))
		return nil, gerrors.Newf("failed to download docker image: %s", err)
	}
	log.Trace(ctx, "End pull image")

	log.Trace(ctx, "Creating docker container", "image:", spec.Image)
	log.Trace(ctx, "Container params ", "mounts", spec.Mounts)
	log.Trace(ctx, "Container command ", "cmd", spec.Commands)
	log.Trace(ctx, "Container entrypoint ", "entrypoint", spec.Entrypoint)

	config := &container.Config{
		Image:        spec.Image,
		Cmd:          spec.Commands,
		Entrypoint:   spec.Entrypoint,
		Tty:          true,
		WorkingDir:   spec.WorkDir,
		Env:          spec.Env,
		ExposedPorts: spec.ExposedPorts,
		Labels:       spec.Labels,
		AttachStdout: true,
		AttachStdin:  true,
	}
	var networkMode container.NetworkMode = "default"
	if spec.AllowHostMode && supportNetworkModeHost() {
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
		Logs:   true,
	})
	if err != nil {
		return gerrors.Wrap(err)
	}
	go func() {
		_, err = io.Copy(r.logs, logs.Reader)
		//_, err = stdcopy.StdCopy(r.logs, r.logs, logs.Reader)
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
		return gerrors.Wrap(ContainerExitedError{info.State.ExitCode})
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

func (r *Engine) pullImageIfAbsent(ctx context.Context, image string, registryAuthBase64 string) error {
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
	reader, err := r.client.ImagePull(ctx, image, types.ImagePullOptions{
		RegistryAuth: registryAuthBase64,
	})
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

func (r *Engine) GetPrebuildName(ctx context.Context, spec *PrebuildSpec) (string, error) {
	err := r.pullImageIfAbsent(ctx, spec.BaseImageName, spec.RegistryAuthBase64)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	info, _, err := r.client.ImageInspectWithRaw(ctx, spec.BaseImageName)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	spec.BaseImageID = info.ID
	return spec.Hash(), nil
}

func (r *Engine) Prebuild(ctx context.Context, spec *PrebuildSpec, imageName string, stoppedCh chan struct{}, logs io.Writer) error {
	if err := PrebuildImage(ctx, r.client, spec, imageName, stoppedCh, logs); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (r *Engine) ImageExists(ctx context.Context, imageName string) (bool, error) {
	summaries, err := r.client.ImageList(ctx, types.ImageListOptions{
		Filters: filters.NewArgs(filters.Arg("reference", imageName)),
	})
	if err != nil {
		return false, gerrors.Wrap(err)
	}
	return len(summaries) != 0, nil
}

func (r *Engine) ExportImageDiff(ctx context.Context, imageName, diffPath string) error {
	if err := Overlay2ExportImageDiff(ctx, r.client, imageName, diffPath); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (r *Engine) ImportImageDiff(ctx context.Context, diffPath string) error {
	if err := Overlay2ImportImageDiff(ctx, diffPath); err != nil {
		return gerrors.Wrap(err)
	}
	if err := r.RestartDaemon(ctx); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (r *Engine) RestartDaemon(ctx context.Context) error {
	log.Trace(ctx, "Restarting docker daemon")
	cmd := exec.Command("systemctl", "restart", "docker")
	if err := cmd.Run(); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func ShellCommands(commands []string) []string {
	if len(commands) == 0 {
		return []string{}
	}
	var sb strings.Builder
	for i, cmd := range commands {
		cmd := strings.TrimSpace(cmd)
		if i > 0 {
			sb.WriteString(" && ")
		}
		if strings.HasSuffix(cmd, "&") {
			sb.WriteString("{ ")
			sb.WriteString(cmd)
			sb.WriteString(" }")
		} else {
			sb.WriteString(cmd)
		}
	}
	return []string{sb.String()}
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
