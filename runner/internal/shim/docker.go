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

type DockerRunner struct {
	client       *docker.Client
	dockerParams DockerParameters
	state        RunnerStatus
}

func NewDockerRunner(dockerParams DockerParameters) (*DockerRunner, error) {
	client, err := docker.NewClientWithOpts(docker.FromEnv, docker.WithAPIVersionNegotiation())
	if err != nil {
		return nil, err
	}

	runner := &DockerRunner{
		client:       client,
		dockerParams: dockerParams,
		state:        Pending,
	}
	return runner, nil
}

func (d *DockerRunner) Run(ctx context.Context, cfg DockerImageConfig) error {
	var err error

	log.Println("Pulling image")
	d.state = Pulling
	if err = pullImage(ctx, d.client, cfg); err != nil {
		d.state = Pending
		fmt.Printf("pullImage error: %s\n", err.Error())
		return err
	}

	log.Println("Creating container")
	d.state = Creating
	containerID, err := createContainer(ctx, d.client, d.dockerParams, cfg)
	if err != nil {
		d.state = Pending
		fmt.Printf("createContainer error: %s\n", err.Error())
		return err
	}

	if !d.dockerParams.DockerKeepContainer() {
		defer func() {
			log.Println("Deleting container")
			err := d.client.ContainerRemove(ctx, containerID, types.ContainerRemoveOptions{Force: true})
			if err != nil {
				log.Printf("ContainerRemove error: %s\n", err.Error())
			}
		}()
	}

	log.Printf("Running container, id=%s\n", containerID)
	d.state = Running
	if err = runContainer(ctx, d.client, containerID); err != nil {
		d.state = Pending
		fmt.Printf("runContainer error: %s\n", err.Error())
		return err
	}

	log.Printf("Container finished successfully, id=%s\n", containerID)

	d.state = Pending
	return nil
}

func (d DockerRunner) GetState() RunnerStatus {
	return d.state
}

func pullImage(ctx context.Context, client docker.APIClient, taskParams DockerImageConfig) error {
	if !strings.Contains(taskParams.ImageName, ":") {
		taskParams.ImageName += ":latest"
	}
	images, err := client.ImageList(ctx, types.ImageListOptions{
		Filters: filters.NewArgs(filters.Arg("reference", taskParams.ImageName)),
	})
	if err != nil {
		return gerrors.Wrap(err)
	}

	// TODO: force pull latset
	if len(images) > 0 && !strings.Contains(taskParams.ImageName, ":latest") {
		return nil
	}

	opts := types.ImagePullOptions{}
	regAuth, _ := taskParams.EncodeRegistryAuth()
	if regAuth != "" {
		opts.RegistryAuth = regAuth
	}

	reader, err := client.ImagePull(ctx, taskParams.ImageName, opts) // todo test registry auth
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = reader.Close() }()

	_, err = io.Copy(io.Discard, reader)
	if err != nil {
		return gerrors.Wrap(err)
	}

	// {"status":"Pulling from clickhouse/clickhouse-server","id":"latest"}
	// {"status":"Digest: sha256:2ff5796c67e8d588273a5f3f84184b9cdaa39a324bcf74abd3652d818d755f8c"}
	// {"status":"Status: Downloaded newer image for clickhouse/clickhouse-server:latest"}

	return nil
}

func createContainer(ctx context.Context, client docker.APIClient, dockerParams DockerParameters, taskParams DockerImageConfig) (string, error) {
	runtime, err := getRuntime(ctx, client)
	if err != nil {
		return "", gerrors.Wrap(err)
	}

	mounts, err := dockerParams.DockerMounts()
	if err != nil {
		return "", gerrors.Wrap(err)
	}

	containerConfig := &container.Config{
		Image:        taskParams.ImageName,
		Cmd:          []string{strings.Join(dockerParams.DockerShellCommands(), " && ")},
		Entrypoint:   []string{"/bin/sh", "-c"},
		ExposedPorts: exposePorts(dockerParams.DockerPorts()...),
	}
	hostConfig := &container.HostConfig{
		NetworkMode:     getNetworkMode(),
		PortBindings:    bindPorts(dockerParams.DockerPorts()...),
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

func (c CLIArgs) DockerKeepContainer() bool {
	return c.Docker.KeepContainer
}

func (c CLIArgs) DockerShellCommands() []string {
	commands := getSSHShellCommands(c.Docker.SSHPort, c.Docker.PublicSSHKey)
	commands = append(commands, fmt.Sprintf("%s %s", DstackRunnerBinaryName, strings.Join(c.getRunnerArgs(), " ")))
	return commands
}

func (c CLIArgs) DockerMounts() ([]mount.Mount, error) {
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

func (c CLIArgs) DockerPorts() []int {
	return []int{c.Runner.HTTPPort, c.Docker.SSHPort}
}
