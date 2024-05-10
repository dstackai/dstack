package shim

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	rt "runtime"
	"strconv"
	"strings"
	"time"

	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/api/types/filters"
	"github.com/docker/docker/api/types/image"
	"github.com/docker/docker/api/types/mount"
	docker "github.com/docker/docker/client"
	"github.com/docker/go-connections/nat"
	"github.com/dstackai/dstack/runner/consts"
	"github.com/icza/backscanner"
	bytesize "github.com/inhies/go-bytesize"
	"github.com/ztrue/tracerr"
)

// TODO: Allow for configuration via cli arguments or environment variables.
const ImagePullTimeout time.Duration = 20 * time.Minute

// Depricated: Remove on next release (0.19)
type ContainerStatus struct {
	ContainerID   string
	ContainerName string
	Status        string
	Running       bool
	OOMKilled     bool
	Dead          bool
	ExitCode      int
	Error         string
}

type JobResult struct {
	Reason        string `json:"reason"`
	ReasonMessage string `json:"reason_message"`
}

type DockerRunner struct {
	client           *docker.Client
	dockerParams     DockerParameters
	currentContainer string
	state            RunnerStatus

	cancelPull context.CancelFunc

	containerStatus ContainerStatus // TODO: remove on next release (0.19)
	executorError   string          // TODO: remove on next release (0.19)
	jobResult       JobResult
}

func NewDockerRunner(dockerParams DockerParameters) (*DockerRunner, error) {
	client, err := docker.NewClientWithOpts(docker.FromEnv, docker.WithAPIVersionNegotiation())
	if err != nil {
		return nil, tracerr.Wrap(err)
	}

	runner := &DockerRunner{
		client:       client,
		dockerParams: dockerParams,
		state:        Pending,
	}
	return runner, nil
}

func (d *DockerRunner) Run(ctx context.Context, cfg TaskConfig) error {
	var err error

	if cfg.SshKey != "" {
		ak := AuthorizedKeys{user: cfg.SshUser}
		if err := ak.AppendPublicKeys([]string{cfg.SshKey}); err != nil {
			return tracerr.Wrap(err)
		}
		defer func(cfg TaskConfig) {
			err := ak.RemovePublicKeys([]string{cfg.SshKey})
			if err != nil {
				log.Printf("Error RemovePublicKeys: %s\n", err.Error())
			}
		}(cfg)
	}

	d.containerStatus = ContainerStatus{
		ContainerName: cfg.ContainerName,
	}
	d.executorError = ""

	pullCtx, cancel := context.WithTimeout(ctx, ImagePullTimeout)
	defer cancel()
	d.cancelPull = cancel

	log.Println("Pulling image")
	d.state = Pulling
	if err = pullImage(pullCtx, d.client, cfg); err != nil {
		d.state = Pending
		errMessage := fmt.Sprintf("pullImage error: %s", err.Error())
		d.containerStatus.Error = errMessage
		log.Print(errMessage + "\n")
		d.jobResult = JobResult{Reason: "CREATING_CONTAINER_ERROR", ReasonMessage: errMessage}
		return err
	}

	runnerDir, err := d.dockerParams.MakeRunnerDir()
	if err != nil {
		d.state = Pending
		errMessage := fmt.Sprintf("Cannot create dir for runner: %s", err.Error())
		d.containerStatus.Error = errMessage
		log.Print(errMessage + "\n")
		d.jobResult = JobResult{Reason: "CREATING_CONTAINER_ERROR", ReasonMessage: errMessage}
		return err
	}

	log.Println("Creating container")
	d.state = Creating
	containerID, err := createContainer(ctx, d.client, runnerDir, d.dockerParams, cfg)
	if err != nil {
		d.state = Pending
		errMessage := fmt.Sprintf("createContainer error: %s", err.Error())
		d.containerStatus.Error = errMessage
		d.jobResult = JobResult{Reason: "CREATING_CONTAINER_ERROR", ReasonMessage: errMessage}
		log.Print(errMessage + "\n")
		return err
	}

	if !d.dockerParams.DockerKeepContainer() {
		defer func() {
			log.Println("Deleting container")
			err := d.client.ContainerRemove(ctx, containerID, container.RemoveOptions{Force: true})
			if err != nil {
				log.Printf("ContainerRemove error: %s\n", err.Error())
			}
		}()
	}

	d.containerStatus, _ = inspectContainer(d.client, containerID)
	d.state = Running
	d.currentContainer = containerID
	d.executorError = ""
	log.Printf("Running container, name=%s, id=%s\n", d.containerStatus.ContainerName, containerID)

	if err = runContainer(ctx, d.client, containerID); err != nil {
		log.Printf("runContainer error: %s\n", err.Error())
		d.state = Pending
		d.containerStatus, _ = inspectContainer(d.client, containerID)
		d.executorError = FindExecutorError(runnerDir)
		d.currentContainer = ""
		var errMessage string = d.containerStatus.Error
		if d.containerStatus.OOMKilled {
			errMessage = "Container killed by OOM"
		}
		d.jobResult = JobResult{Reason: "CONTAINER_EXITED_WITH_ERROR", ReasonMessage: errMessage}
		return err
	}

	log.Printf("Container finished successfully, name=%s, id=%s", d.containerStatus.ContainerName, containerID)
	d.containerStatus, _ = inspectContainer(d.client, containerID)
	d.executorError = FindExecutorError(runnerDir)
	d.state = Pending
	d.currentContainer = ""

	jobResult := JobResult{Reason: "DONE_BY_RUNNER"}
	if d.containerStatus.ExitCode != 0 {
		jobResult = JobResult{Reason: "CONTAINER_EXITED_WITH_ERROR", ReasonMessage: d.containerStatus.Error}
	}
	d.jobResult = jobResult

	return nil
}

func (d *DockerRunner) Stop(force bool) {
	if d.state == Pulling && d.currentContainer == "" {
		d.cancelPull()
		return
	}

	stopOptions := container.StopOptions{}
	if force {
		timeout := int(0)
		stopOptions.Timeout = &timeout
	}

	err := d.client.ContainerStop(context.Background(), d.currentContainer, stopOptions)
	if err != nil {
		log.Printf("Failed to stop container: %s", err)
	}
}

func (d DockerRunner) GetState() (RunnerStatus, ContainerStatus, string, JobResult) {
	return d.state, d.containerStatus, d.executorError, d.jobResult
}

func pullImage(ctx context.Context, client docker.APIClient, taskConfig TaskConfig) error {
	if !strings.Contains(taskConfig.ImageName, ":") {
		taskConfig.ImageName += ":latest"
	}
	images, err := client.ImageList(ctx, image.ListOptions{
		Filters: filters.NewArgs(filters.Arg("reference", taskConfig.ImageName)),
	})
	if err != nil {
		return tracerr.Wrap(err)
	}

	// TODO: force pull latset
	if len(images) > 0 && !strings.Contains(taskConfig.ImageName, ":latest") {
		return nil
	}

	opts := image.PullOptions{}
	regAuth, _ := taskConfig.EncodeRegistryAuth()
	if regAuth != "" {
		opts.RegistryAuth = regAuth
	}

	startTime := time.Now()
	reader, err := client.ImagePull(ctx, taskConfig.ImageName, opts)
	if err != nil {
		return tracerr.Wrap(err)
	}
	defer func() { _ = reader.Close() }()

	current := make(map[string]uint)
	total := make(map[string]uint)

	type ProgressDetail struct {
		Current uint `json:"current"`
		Total   uint `json:"total"`
	}
	type Progress struct {
		Id             string         `json:"id"`
		Status         string         `json:"status"`
		ProgressDetail ProgressDetail `json:"progressDetail"` //nolint:tagliatelle
	}

	var status bool

	scanner := bufio.NewScanner(reader)
	for scanner.Scan() {
		line := scanner.Bytes()
		var progressRow Progress
		if err := json.Unmarshal(line, &progressRow); err != nil {
			continue
		}
		if progressRow.Status == "Downloading" {
			current[progressRow.Id] = progressRow.ProgressDetail.Current
			total[progressRow.Id] = progressRow.ProgressDetail.Total
		}
		if progressRow.Status == "Download complete" {
			current[progressRow.Id] = total[progressRow.Id]
		}
		if strings.HasPrefix(progressRow.Status, "Status:") {
			status = true
			log.Println(progressRow.Status)
		}
	}

	duration := time.Since(startTime)

	var currentBytes uint
	var totalBytes uint
	for _, v := range current {
		currentBytes += v
	}
	for _, v := range total {
		totalBytes += v
	}

	speed := bytesize.New(float64(currentBytes) / duration.Seconds())
	if status && currentBytes == totalBytes {
		log.Printf("Image Pull successfully downloaded: %d bytes (%s/s)", currentBytes, speed)
	} else {
		log.Printf("Image Pull interrupted: downloaded %d bytes out of %d (%s/s)", currentBytes, totalBytes, speed)
	}

	err = ctx.Err()
	if err != nil {
		return tracerr.Errorf("imagepull interrupted: downloaded %d bytes out of %d (%s/s): %w", currentBytes, totalBytes, speed, err)
	}
	return nil
}

func createContainer(ctx context.Context, client docker.APIClient, runnerDir string, dockerParams DockerParameters, taskConfig TaskConfig) (string, error) {
	timeout := int(0)
	stopOptions := container.StopOptions{Timeout: &timeout}
	err := client.ContainerStop(ctx, taskConfig.ContainerName, stopOptions)
	if err != nil {
		log.Printf("Cleanup routine: Cannot stop container: %s", err)
	}

	removeOptions := container.RemoveOptions{Force: true}
	err = client.ContainerRemove(ctx, taskConfig.ContainerName, removeOptions)
	if err != nil {
		log.Printf("Cleanup routine: Cannot remove container: %s", err)
	}

	gpuRequest, err := requestGpuIfAvailable(ctx, client)
	if err != nil {
		return "", tracerr.Wrap(err)
	}
	mounts, err := dockerParams.DockerMounts(runnerDir)
	if err != nil {
		return "", tracerr.Wrap(err)
	}

	containerConfig := &container.Config{
		Image:        taskConfig.ImageName,
		Cmd:          []string{strings.Join(dockerParams.DockerShellCommands(taskConfig.PublicKeys), " && ")},
		Entrypoint:   []string{"/bin/sh", "-c"},
		ExposedPorts: exposePorts(dockerParams.DockerPorts()...),
	}
	hostConfig := &container.HostConfig{
		NetworkMode:     getNetworkMode(),
		PortBindings:    bindPorts(dockerParams.DockerPorts()...),
		PublishAllPorts: true,
		Sysctls:         map[string]string{},
		Resources: container.Resources{
			DeviceRequests: gpuRequest,
		},
		Mounts:  mounts,
		ShmSize: taskConfig.ShmSize,
	}
	resp, err := client.ContainerCreate(ctx, containerConfig, hostConfig, nil, nil, taskConfig.ContainerName)
	if err != nil {
		return "", tracerr.Wrap(err)
	}
	return resp.ID, nil
}

func runContainer(ctx context.Context, client docker.APIClient, containerID string) error {
	if err := client.ContainerStart(ctx, containerID, container.StartOptions{}); err != nil {
		return tracerr.Wrap(err)
	}

	waitCh, errorCh := client.ContainerWait(ctx, containerID, "")
	select {
	case <-waitCh:
	case err := <-errorCh:
		return tracerr.Wrap(err)
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
		"sed -ie '1s@^@export PATH=\"'\"$PATH\"':$PATH\"\\n\\n@' ~/.profile",
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

func requestGpuIfAvailable(ctx context.Context, client docker.APIClient) ([]container.DeviceRequest, error) {
	info, err := client.Info(ctx)
	if err != nil {
		return nil, tracerr.Wrap(err)
	}

	for runtime := range info.Runtimes {
		if runtime == consts.NVIDIA_RUNTIME {
			return []container.DeviceRequest{
				{Capabilities: [][]string{{"gpu"}}, Count: -1}, // --gpus=all
			}, nil
		}
	}

	return nil, nil
}

/* DockerParameters interface implementation for CLIArgs */

func (c CLIArgs) DockerKeepContainer() bool {
	return c.Docker.KeepContainer
}

func (c CLIArgs) DockerShellCommands(publicKeys []string) []string {
	concatinatedPublicKeys := c.Docker.ConcatinatedPublicSSHKeys
	if len(publicKeys) > 0 {
		concatinatedPublicKeys = strings.Join(publicKeys, "\n")
	}
	commands := getSSHShellCommands(c.Docker.SSHPort, concatinatedPublicKeys)
	commands = append(commands, fmt.Sprintf("%s %s", DstackRunnerBinaryName, strings.Join(c.getRunnerArgs(), " ")))
	return commands
}

func (c CLIArgs) DockerMounts(hostRunnerDir string) ([]mount.Mount, error) {
	return []mount.Mount{
		{
			Type:   mount.TypeBind,
			Source: hostRunnerDir,
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

func (c CLIArgs) MakeRunnerDir() (string, error) {
	runnerTemp := filepath.Join(c.Shim.HomeDir, "runners", time.Now().Format("20060102-150405"))
	if err := os.MkdirAll(runnerTemp, 0o755); err != nil {
		return "", tracerr.Wrap(err)
	}
	return runnerTemp, nil
}

func inspectContainer(client *docker.Client, containerID string) (ContainerStatus, error) {
	inspection, err := client.ContainerInspect(context.Background(), containerID)
	if err != nil {
		s := ContainerStatus{}
		return s, err
	}
	containerStatus := ContainerStatus{
		ContainerID:   containerID,
		ContainerName: strings.TrimLeft(inspection.Name, "/"),
		Status:        inspection.State.Status,
		Running:       inspection.State.Running,
		OOMKilled:     inspection.State.OOMKilled,
		Dead:          inspection.State.Dead,
		ExitCode:      inspection.State.ExitCode,
		Error:         inspection.State.Error,
	}
	return containerStatus, nil
}

func FindExecutorError(runnerDir string) string {
	filename := filepath.Join(runnerDir, consts.RunnerLogFileName)
	file, err := os.Open(filename)
	if err != nil {
		log.Printf("Cannot open file %s: %s\n", filename, err)
		return ""
	}
	defer file.Close()

	fileStatus, err := file.Stat()
	if err != nil {
		log.Printf("Cannot stat file %s: %s\n", filename, err)
		return ""
	}

	scanner := backscanner.New(file, int(fileStatus.Size()))
	what := []byte(consts.ExecutorFailedSignature)
	for {
		line, _, err := scanner.LineBytes()
		if err != nil {
			if err == io.EOF {
				return "" // consts.ExecutorFailedSignature is not found in file
			}
			log.Printf("FindExecutorError scan error: %s\n", err)
			return ""
		}
		if bytes.Contains(line, what) {
			return string(line)
		}
	}
}
