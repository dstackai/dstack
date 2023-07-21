package docker

import (
	"context"
	"fmt"
	"io"
	"os/exec"
	"runtime"
	"strings"

	"github.com/docker/docker/api/types/mount"
	"github.com/docker/docker/pkg/jsonmessage"
	"github.com/dstackai/dstack/runner/internal/environment"
	"github.com/dstackai/dstack/runner/internal/models"

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

func (e *Engine) DockerClient() docker.APIClient {
	return e.client
}

func (e *Engine) DockerRuntime() string {
	return e.runtime
}

func (e *Engine) CPU() int {
	return e.nCpu
}

func (e *Engine) MemMiB() uint64 {
	return e.memTotalMiB
}

type Container struct {
	client      docker.APIClient
	containerID string
	logs        io.Writer
}

func (e *Engine) Create(ctx context.Context, spec *Spec, logs io.Writer) (*Container, error) {
	container, err := e.CreateNamed(ctx, spec, "", logs)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return container, nil
}

func (e *Engine) CreateNamed(ctx context.Context, spec *Spec, containerName string, logs io.Writer) (*Container, error) {
	log.Trace(ctx, "Start pull image")
	err := e.pullImageIfAbsent(ctx, spec.Image, spec.RegistryAuthBase64, logs)
	if err != nil {
		log.Error(ctx, fmt.Sprintf("failed to download docker image: %s", err))
		return nil, gerrors.Newf("failed to download docker image: %s", err)
	}
	log.Trace(ctx, "End pull image")

	log.Trace(ctx, "Creating docker container", "image", spec.Image)
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
		Runtime:         e.runtime,
		Mounts:          spec.Mounts,
	}
	resp, err := e.client.ContainerCreate(ctx, config, hostConfig, nil, nil, containerName)
	if err != nil {
		log.Error(ctx, fmt.Sprintf("failed to create docker container: %s", err))
		return nil, gerrors.Wrap(err)
	}
	return &Container{
		client:      e.client,
		containerID: resp.ID,
		logs:        logs,
	}, nil
}

func (e *Engine) Get(ctx context.Context, containerName string, logs io.Writer) (*Container, error) {
	return &Container{
		client: e.client,
		// FIXME: containerName works like containerID for starting container, but it's really not
		containerID: containerName,
		logs:        logs,
	}, nil
}

func (c *Container) Run(ctx context.Context) error {
	log.Trace(ctx, "Starting docker container")
	if err := c.client.ContainerStart(ctx, c.containerID, types.ContainerStartOptions{}); err != nil {
		log.Error(ctx, fmt.Sprintf("failed to start docker container: %s", err))
		return gerrors.Newf("failed to start container: %s", err)
	}

	if c.logs != nil {
		err := c.LogsWS(ctx)
		if err != nil {
			return gerrors.Wrap(err)
		}
	}
	return nil
}

func (c *Container) Logs(ctx context.Context) error {
	opts := types.ContainerLogsOptions{
		ShowStdout: true,
		ShowStderr: true,
		Follow:     true,
	}
	logs, err := c.client.ContainerLogs(ctx, c.containerID, opts)
	if err != nil {
		log.Error(ctx, fmt.Sprintf("failed to stream container logs: %s", err))
		return gerrors.Newf("failed to stream container logs: %s", err)
	}
	go func() {
		//_, err = io.Copy(r.logs, logs)
		_, err = stdcopy.StdCopy(c.logs, c.logs, logs)
		if err != nil {
			log.Error(ctx, "failed to stream container logs", "err", gerrors.Wrap(err))
		}
		_ = logs.Close()
	}()
	return nil
}

func (c *Container) LogsWS(ctx context.Context) error {
	logs, err := c.client.ContainerAttach(ctx, c.containerID, types.ContainerAttachOptions{
		Stream: true,
		Stdout: true,
		Stderr: true,
		Logs:   true,
	})
	if err != nil {
		return gerrors.Wrap(err)
	}
	go func() {
		_, err = io.Copy(c.logs, logs.Reader)
		if err != nil {
			log.Error(ctx, "failed to stream container logs", "err", gerrors.Wrap(err))
		}
		logs.Close()
	}()
	return nil
}

func (r *Container) Wait(ctx context.Context) error {
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

func (r *Container) ForceStop(ctx context.Context) error {
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

func (r *Container) Stop(ctx context.Context, remove bool) error {
	log.Trace(ctx, "Stopping container", "containerID", r.containerID)
	err := r.client.ContainerStop(ctx, r.containerID, nil)
	if err != nil {
		return gerrors.Wrap(err)
	}
	if remove {
		log.Trace(ctx, "Removing container", "containerID", r.containerID)
		removeOpts := types.ContainerRemoveOptions{
			Force: true,
		}
		err = r.client.ContainerRemove(ctx, r.containerID, removeOpts)
		if err != nil {
			return gerrors.Wrap(err)
		}
	}
	return nil
}

func (e *Engine) pullImageIfAbsent(ctx context.Context, image string, registryAuthBase64 string, logs io.Writer) error {
	if image == "" {
		return gerrors.New("given image value is empty")
	}

	summaries, err := e.client.ImageList(ctx, types.ImageListOptions{
		Filters: filters.NewArgs(filters.Arg("reference", image)),
	})
	if err != nil {
		return gerrors.Wrap(err)
	}

	if len(summaries) != 0 {
		return nil
	}
	reader, err := e.client.ImagePull(ctx, image, types.ImagePullOptions{
		RegistryAuth: registryAuthBase64,
	})
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = reader.Close() }()

	if logs != nil {
		if err = jsonmessage.DisplayJSONMessagesStream(reader, logs, 0, false, nil); err != nil {
			return gerrors.Wrap(err)
		}
	} else {
		buf, err := io.ReadAll(reader)
		if err != nil {
			return gerrors.Wrap(err)
		}
		log.Trace(ctx, "Image pull stdout", "stdout", string(buf))
	}
	return nil
}

func (e *Engine) NewBuildSpec(ctx context.Context, job *models.Job, spec *Spec, secrets map[string]string, repoPath string, logs io.Writer) (*BuildSpec, error) {
	err := e.pullImageIfAbsent(ctx, spec.Image, spec.RegistryAuthBase64, logs)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	baseImage, _, err := e.client.ImageInspectWithRaw(ctx, spec.Image)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	daemonInfo, err := e.client.Info(ctx)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}

	commands := append([]string{}, job.BuildCommands...)
	commands = append(commands, job.OptionalBuildCommands...)
	env := environment.New()
	env.AddMapString(secrets)

	buildSpec := &BuildSpec{
		BaseImageName:      spec.Image,
		BaseImageID:        baseImage.ID,
		WorkDir:            spec.WorkDir,
		ConfigurationPath:  job.ConfigurationPath,
		ConfigurationType:  job.ConfigurationType,
		Commands:           ShellCommands(InsertEnvs(commands, job.Environment)),
		Entrypoint:         spec.Entrypoint,
		Env:                env.ToSlice(),
		RegistryAuthBase64: spec.RegistryAuthBase64,
		RepoPath:           repoPath,
		RepoId:             job.RepoId,
		ShmSize:            spec.ShmSize,
	}
	if daemonInfo.Architecture == "aarch64" {
		buildSpec.Platform = "arm64"
	} else {
		buildSpec.Platform = "amd64"
	}
	return buildSpec, nil
}

func (e *Engine) Build(ctx context.Context, spec *BuildSpec, imageName string, stoppedCh chan bool, logs io.Writer) error {
	containerSpec := &Spec{
		Image:              spec.BaseImageName,
		RegistryAuthBase64: spec.RegistryAuthBase64,
		WorkDir:            spec.WorkDir,
		Commands:           spec.Commands,
		Entrypoint:         spec.Entrypoint,
		Env:                spec.Env,
		ShmSize:            spec.ShmSize,
		Mounts: []mount.Mount{
			{
				Type:     mount.TypeBind,
				Source:   spec.RepoPath,
				Target:   "/workflow",
				ReadOnly: true,
			},
		},
	}
	dockerRuntime, err := e.Create(ctx, containerSpec, logs)
	if err != nil {
		return gerrors.Wrap(err)
	}
	if err = dockerRuntime.Run(ctx); err != nil {
		return gerrors.Wrap(err)
	}
	defer func() {
		_ = e.client.ContainerRemove(ctx, dockerRuntime.containerID, types.ContainerRemoveOptions{Force: true})
	}()

	statusCh, errCh := e.client.ContainerWait(ctx, dockerRuntime.containerID, container.WaitConditionNotRunning)
	select {
	// todo timeout
	case err := <-errCh:
		if err != nil {
			return gerrors.Wrap(err)
		}
	case <-stoppedCh:
		err := e.client.ContainerKill(ctx, dockerRuntime.containerID, "SIGTERM")
		if err != nil {
			return gerrors.Wrap(err)
		}
	case <-statusCh:
	}

	info, err := e.client.ContainerInspect(ctx, dockerRuntime.containerID)
	if err != nil {
		return gerrors.Wrap(err)
	}
	if info.State.ExitCode != 0 {
		return gerrors.Wrap(ContainerExitedError{info.State.ExitCode})
	}
	log.Trace(ctx, "Committing build image", "image", imageName)
	_, err = e.client.ContainerCommit(ctx, dockerRuntime.containerID, types.ContainerCommitOptions{Reference: imageName})
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (e *Engine) ImageExists(ctx context.Context, imageName string) (bool, error) {
	summaries, err := e.client.ImageList(ctx, types.ImageListOptions{
		Filters: filters.NewArgs(filters.Arg("reference", imageName)),
	})
	if err != nil {
		return false, gerrors.Wrap(err)
	}
	return len(summaries) != 0, nil
}

func (e *Engine) ExportImageDiff(ctx context.Context, imageName, diffPath string) error {
	if err := Overlay2ExportImageDiff(ctx, e.client, imageName, diffPath); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (e *Engine) ImportImageDiff(ctx context.Context, diffPath string) error {
	if err := Overlay2ImportImageDiff(ctx, diffPath); err != nil {
		return gerrors.Wrap(err)
	}
	if err := e.RestartDaemon(ctx); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (e *Engine) RestartDaemon(ctx context.Context) error {
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

// InsertEnvs allows interpolation of env variables (e.g. PATH=/foo/bar:$PATH)
func InsertEnvs(commands []string, envs map[string]string) []string {
	output := make([]string, 0)
	for name, val := range envs {
		output = append(output, fmt.Sprintf("export %s=%s", name, val))
	}
	return append(output, commands...)
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
