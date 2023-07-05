package container

import (
	"bytes"
	"context"
	"crypto/sha256"
	"fmt"
	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/api/types/mount"
	docker "github.com/docker/docker/client"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"io"
)

type BuildSpec struct {
	BaseImageID       string
	WorkDir           string
	ConfigurationPath string
	ConfigurationType string

	Commands           []string
	Entrypoint         []string
	Env                []string
	BaseImageName      string
	RegistryAuthBase64 string
	RepoPath           string
	Platform           string
	RepoId             string
}

func BuildImage(ctx context.Context, client docker.APIClient, spec *BuildSpec, imageName string, stoppedCh chan struct{}, logs io.Writer) error {
	stopTimeout := 10 * 60
	config := &container.Config{
		Image:       spec.BaseImageID,
		WorkingDir:  spec.WorkDir,
		Cmd:         spec.Commands,
		Entrypoint:  spec.Entrypoint,
		Env:         spec.Env,
		StopTimeout: &stopTimeout,
		Tty:         true,
	}
	hostConfig := &container.HostConfig{
		Mounts: []mount.Mount{
			{
				Type:     mount.TypeBind,
				Source:   spec.RepoPath,
				Target:   "/workflow",
				ReadOnly: true,
			},
		},
	}
	createResp, err := client.ContainerCreate(ctx, config, hostConfig, nil, nil, "")
	if err != nil {
		return gerrors.Wrap(err)
	}
	err = client.ContainerStart(ctx, createResp.ID, types.ContainerStartOptions{})
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() {
		_ = client.ContainerRemove(ctx, createResp.ID, types.ContainerRemoveOptions{Force: true})
	}()

	log.Trace(ctx, "Streaming build logs")
	attachResp, err := client.ContainerAttach(ctx, createResp.ID, types.ContainerAttachOptions{
		Stream: true,
		Stdout: true,
		Stderr: true,
		Logs:   true,
	})
	if err != nil {
		return gerrors.Wrap(err)
	}
	go func() {
		_, err := io.Copy(logs, attachResp.Reader)
		if err != nil {
			log.Error(ctx, "Failed to stream build logs", "err", err)
		}
	}()

	statusCh, errCh := client.ContainerWait(ctx, createResp.ID, container.WaitConditionNotRunning)
	if err != nil {
		return gerrors.Wrap(err)
	}
	select {
	case err := <-errCh:
		if err != nil {
			return gerrors.Wrap(err)
		}
	case <-stoppedCh:
		err := client.ContainerKill(ctx, createResp.ID, "SIGTERM")
		if err != nil {
			return gerrors.Wrap(err)
		}
	case <-statusCh:
	}
	info, err := client.ContainerInspect(ctx, createResp.ID)
	if err != nil {
		return gerrors.Wrap(err)
	}
	if info.State.ExitCode != 0 {
		return gerrors.Wrap(ContainerExitedError{info.State.ExitCode})
	}
	log.Trace(ctx, "Committing build image", "image", imageName)
	_, err = client.ContainerCommit(ctx, createResp.ID, types.ContainerCommitOptions{Reference: imageName})
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (s *BuildSpec) Hash() string {
	var buffer bytes.Buffer
	buffer.WriteString(s.BaseImageID)
	buffer.WriteString("\n")
	buffer.WriteString(s.WorkDir)
	buffer.WriteString("\n")
	buffer.WriteString(s.ConfigurationPath)
	buffer.WriteString("\n")
	buffer.WriteString(s.ConfigurationType)
	buffer.WriteString("\n")
	return fmt.Sprintf("%x", sha256.Sum256(buffer.Bytes()))
}
