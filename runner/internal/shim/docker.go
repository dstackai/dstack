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

func RunDocker(ctx context.Context, config DockerConfig) error {
	client, err := docker.NewClientWithOpts(docker.FromEnv, docker.WithAPIVersionNegotiation())
	if err != nil {
		return err
	}

	// todo run server & wait for credentials
	// todo serve pulling status
	//if config.WithAuth {
	//	return gerrors.New("not implemented")
	//}

	log.Println("Pulling image")
	if err = config.PullImage(ctx, client); err != nil {
		return gerrors.Wrap(err)
	}
	log.Println("Creating container")
	containerID, err := config.CreateContainer(ctx, client)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() {
		log.Println("Doing cleanup")
		_ = config.Cleanup(ctx, client, containerID)
	}()
	log.Printf("Running container, id=%s\n", containerID)
	if err = config.RunContainer(ctx, client, containerID); err != nil {
		return gerrors.Wrap(err)
	}
	log.Println("Container finished successfully")
	return nil
}

func (c *DockerParameters) PullImage(ctx context.Context, client docker.APIClient) error {
	imageName := c.ImageName
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

	reader, err := client.ImagePull(ctx, imageName, types.ImagePullOptions{RegistryAuth: c.RegistryAuthBase64})
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = reader.Close() }()

	_, err = io.ReadAll(reader)
	return gerrors.Wrap(err)
}

func (c *DockerParameters) CreateContainer(ctx context.Context, client docker.APIClient) (string, error) {
	runtime, err := getRuntime(ctx, client)
	if err != nil {
		return "", gerrors.Wrap(err)
	}

	runnerMount, err := c.Runner.GetDockerMount()
	if err != nil {
		return "", gerrors.Wrap(err)
	}

	commands := make([]string, 0)
	commands = append(commands, c.runOpenSSHServer()...)
	commands = append(commands, c.Runner.GetDockerCommands()...)

	var mounts = make([]mount.Mount, 0)
	if c.DstackHome != "" {
		mountPath := filepath.Join(c.DstackHome, "runners", time.Now().Format("20060102-150405"))
		if err = os.MkdirAll(mountPath, 0755); err != nil {
			return "", gerrors.Wrap(err)
		}
		mounts = append(mounts, mount.Mount{
			Type:   mount.TypeBind,
			Source: mountPath,
			Target: c.Runner.GetTempDir(),
		})
	}
	if runnerMount != nil {
		mounts = append(mounts, *runnerMount)
	}

	containerConfig := &container.Config{
		Image:        c.ImageName,
		Cmd:          []string{strings.Join(commands, " && ")},
		Entrypoint:   []string{"/bin/sh", "-c"},
		ExposedPorts: exposePorts(c.OpenSSHPort),
	}
	hostConfig := &container.HostConfig{
		NetworkMode:     getNetworkMode(),
		PortBindings:    bindPorts(c.OpenSSHPort),
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

func (c *DockerParameters) RunContainer(ctx context.Context, client docker.APIClient, containerID string) error {
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

func (c *DockerParameters) Cleanup(ctx context.Context, client docker.APIClient, containerID string) error {
	if !c.KeepContainer {
		log.Println("Deleting container")
		return gerrors.Wrap(client.ContainerRemove(ctx, containerID, types.ContainerRemoveOptions{Force: true}))
	}
	return nil
}

func (c *DockerParameters) runOpenSSHServer() []string {
	return []string{
		// note: &> redirection doesn't work in /bin/sh
		// check in sshd is here, install if not
		"if ! command -v sshd >/dev/null 2>&1; then { apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y openssh-server; } || { yum -y install openssh-server; }; fi",
		// prohibit password authentication
		"sed -i \"s/.*PasswordAuthentication.*/PasswordAuthentication no/g\" /etc/ssh/sshd_config",
		// create ssh dirs and add public key
		"mkdir -p /run/sshd ~/.ssh",
		"chmod 700 ~/.ssh",
		fmt.Sprintf("echo '%s' > ~/.ssh/authorized_keys", c.PublicSSHKey),
		"chmod 600 ~/.ssh/authorized_keys",
		// preserve environment variables for SSH clients
		"env >> ~/.ssh/environment",
		"echo \"export PATH=$PATH\" >> ~/.profile",
		// regenerate host keys
		"rm -rf /etc/ssh/ssh_host_*",
		"ssh-keygen -A > /dev/null",
		// start sshd
		fmt.Sprintf("/usr/sbin/sshd -p %d -o PermitUserEnvironment=yes", c.OpenSSHPort),
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
