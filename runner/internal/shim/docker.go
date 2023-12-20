package shim

import (
	"context"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	rt "runtime"
	"strconv"
	"strings"
	"time"

	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/api/types/filters"
	"github.com/docker/docker/api/types/mount"
	docker "github.com/docker/docker/client"
	"github.com/docker/go-connections/nat"
	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/gerrors"
)

func RunDocker(ctx context.Context, params DockerParameters, serverAPI APIAdapter) error {
	client, err := docker.NewClientWithOpts(docker.FromEnv, docker.WithAPIVersionNegotiation())
	if err != nil {
		return err
	}

	log.Println("Waiting for registry auth")
	registryAuth := serverAPI.GetRegistryAuth()
	serverAPI.SetState(Pulling)

	log.Println("Pulling image")
	imageName := params.DockerImageName()
	if imageName == "" {
		imageName = registryAuth.ImageName
	}
	if err = pullImage(ctx, client, imageName, registryAuth); err != nil {
		return gerrors.Wrap(err)
	}

	log.Println("Creating container")
	containerID, err := createContainer(ctx, client, params)
	if err != nil {
		return gerrors.Wrap(err)
	}
	if !params.DockerKeepContainer() {
		defer func() {
			log.Println("Deleting container")
			_ = client.ContainerRemove(ctx, containerID, types.ContainerRemoveOptions{Force: true})
		}()
	}

	serverAPI.SetState(Running)
	log.Printf("Running container, id=%s\n", containerID)
	if err = runContainer(ctx, client, containerID); err != nil {
		return gerrors.Wrap(err)
	}
	log.Println("Container finished successfully")
	return nil
}

func pullImage(ctx context.Context, client docker.APIClient, imageName string, imagePullConfig ImagePullConfig) error {
	if !strings.Contains(imageName, ":") {
		imageName += ":latest"
	}
	images, err := client.ImageList(ctx, types.ImageListOptions{
		Filters: filters.NewArgs(filters.Arg("reference", imageName)),
	})
	if err != nil {
		return gerrors.Wrap(err)
	}
	if len(images) > 0 {
		return nil
	}

	opts := types.ImagePullOptions{}
	regAuth, _ := imagePullConfig.EncodeRegistryAuth()
	if regAuth != "" {
		opts.RegistryAuth = regAuth
	}

	reader, err := client.ImagePull(ctx, imageName, opts) // todo test registry auth
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = reader.Close() }()

	_, err = io.ReadAll(reader)
	return gerrors.Wrap(err)
}

func createContainer(ctx context.Context, client docker.APIClient, params DockerParameters) (string, error) {
	runtime, err := getRuntime(ctx, client)
	if err != nil {
		return "", gerrors.Wrap(err)
	}

	mounts, err := params.DockerMounts()
	if err != nil {
		return "", gerrors.Wrap(err)
	}

	containerConfig := &container.Config{
		Image:        params.DockerImageName(),
		Cmd:          []string{strings.Join(params.DockerShellCommands(), " && ")},
		Entrypoint:   []string{"/bin/sh", "-c"},
		ExposedPorts: exposePorts(params.DockerPorts()...),
	}
	hostConfig := &container.HostConfig{
		NetworkMode:     getNetworkMode(),
		PortBindings:    bindPorts(params.DockerPorts()...),
		PublishAllPorts: true,
		Sysctls:         map[string]string{},
		Runtime:         runtime,
		Mounts:          mounts,
	}
	resp, err := client.ContainerCreate(ctx, containerConfig, hostConfig, nil, nil, "")
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	return resp.ID, nil
}

func runContainer(ctx context.Context, client docker.APIClient, containerID string) error {
	if err := client.ContainerStart(ctx, containerID, types.ContainerStartOptions{}); err != nil {
		return gerrors.Wrap(err)
	}
	waitCh, errorCh := client.ContainerWait(ctx, containerID, "")
	select {
	case <-waitCh:
	case err := <-errorCh:
		return gerrors.Wrap(err)
	}
	return nil
}

func getSSHShellCommands(openSSHPort int, publicSSHKey string) []string {
	return []string{
		// note: &> redirection doesn't work in /bin/sh
		// check in sshd is here, install if not
		"if ! command -v sshd >/dev/null 2>&1; then { apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y openssh-server; } || { yum -y install openssh-server; }; fi",
		// prohibit password authentication
		"sed -i \"s/.*PasswordAuthentication.*/PasswordAuthentication no/g\" /etc/ssh/sshd_config",
		// create ssh dirs and add public key
		"mkdir -p /run/sshd ~/.ssh",
		"chmod 700 ~/.ssh",
		fmt.Sprintf("echo '%s' > ~/.ssh/authorized_keys", publicSSHKey),
		"chmod 600 ~/.ssh/authorized_keys",
		// preserve environment variables for SSH clients
		"env >> ~/.ssh/environment",
		"echo \"export PATH=$PATH\" >> ~/.profile",
		// regenerate host keys
		"rm -rf /etc/ssh/ssh_host_*",
		"ssh-keygen -A > /dev/null",
		// start sshd
		fmt.Sprintf("/usr/sbin/sshd -p %d -o PermitUserEnvironment=yes", openSSHPort),
	}
}

func exposePorts(ports ...int) nat.PortSet {
	portSet := make(nat.PortSet)
	for _, port := range ports {
		portSet[nat.Port(fmt.Sprintf("%d/tcp", port))] = struct{}{}
	}
	return portSet
}

// bindPorts does identity mapping only
func bindPorts(ports ...int) nat.PortMap {
	portMap := make(nat.PortMap)
	for _, port := range ports {
		portMap[nat.Port(fmt.Sprintf("%d/tcp", port))] = []nat.PortBinding{
			{
				HostIP:   "0.0.0.0",
				HostPort: strconv.Itoa(port),
			},
		}
	}
	return portMap
}

func getNetworkMode() container.NetworkMode {
	if rt.GOOS == "linux" {
		return "host"
	}
	return "default"
}

func getRuntime(ctx context.Context, client docker.APIClient) (string, error) {
	info, err := client.Info(ctx)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	for name := range info.Runtimes {
		if name == consts.NVIDIA_RUNTIME {
			return name, nil
		}
	}
	return info.DefaultRuntime, nil
}

/* DockerParameters interface implementation for CLIArgs */

func (c *CLIArgs) DockerImageName() string {
	return c.Docker.ImageName
}

func (c *CLIArgs) DockerKeepContainer() bool {
	return c.Docker.KeepContainer
}

func (c *CLIArgs) DockerShellCommands() []string {
	commands := getSSHShellCommands(c.Docker.SSHPort, c.Docker.PublicSSHKey)
	commands = append(commands, fmt.Sprintf("%s %s", DstackRunnerBinaryName, strings.Join(c.getRunnerArgs(), " ")))
	return commands
}

func (c *CLIArgs) DockerMounts() ([]mount.Mount, error) {
	runnerTemp := filepath.Join(c.Shim.HomeDir, "runners", time.Now().Format("20060102-150405"))
	if err := os.MkdirAll(runnerTemp, 0755); err != nil {
		return nil, gerrors.Wrap(err)
	}

	return []mount.Mount{
		{
			Type:   mount.TypeBind,
			Source: runnerTemp,
			Target: c.Runner.TempDir,
		},
		{
			Type:   mount.TypeBind,
			Source: c.Runner.BinaryPath,
			Target: DstackRunnerBinaryName,
		},
	}, nil
}

func (c *CLIArgs) DockerPorts() []int {
	return []int{c.Runner.HTTPPort, c.Docker.SSHPort}
}
