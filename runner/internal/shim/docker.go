package shim

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"os/exec"
	"os/user"
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
	"github.com/docker/docker/pkg/stdcopy"
	"github.com/docker/go-connections/nat"
	"github.com/docker/go-units"
	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/shim/backends"
	"github.com/icza/backscanner"
	bytesize "github.com/inhies/go-bytesize"
	"github.com/ztrue/tracerr"
)

// TODO: Allow for configuration via cli arguments or environment variables.
const ImagePullTimeout time.Duration = 20 * time.Minute

const (
	// Set to "true" on containers spawned by DockerRunner, used for identification.
	LabelKeyIsRun  = "ai.dstack.shim.is-run"
	LabelValueTrue = "true"
)

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
		ak := AuthorizedKeys{user: cfg.SshUser, lookup: user.Lookup}
		if err := ak.AppendPublicKeys([]string{cfg.SshKey}); err != nil {
			d.state = Pending
			errMessage := fmt.Sprintf("ak.AppendPublicKeys error: %s", err.Error())
			d.containerStatus.Error = errMessage
			log.Println(errMessage)
			d.jobResult = JobResult{Reason: "EXECUTOR_ERROR", ReasonMessage: errMessage}
			return tracerr.Wrap(err)
		}
		defer func(cfg TaskConfig) {
			err := ak.RemovePublicKeys([]string{cfg.SshKey})
			if err != nil {
				log.Printf("Error RemovePublicKeys: %s\n", err.Error())
			}
		}(cfg)
	}

	log.Println("Preparing volumes")
	// defer unmountVolumes() before calling prepareVolumes(), as the latter
	// may fail when some volumes are already mounted; if the volume is not mounted,
	// unmountVolumes() simply skips it
	defer func() { _ = unmountVolumes(cfg) }()
	err = prepareVolumes(cfg)
	if err != nil {
		d.state = Pending
		errMessage := fmt.Sprintf("prepareVolumes error: %s", err.Error())
		d.containerStatus.Error = errMessage
		log.Println(errMessage)
		d.jobResult = JobResult{Reason: "EXECUTOR_ERROR", ReasonMessage: errMessage}
		return tracerr.Wrap(err)
	}
	err = prepareInstanceMountPoints(cfg)
	if err != nil {
		d.state = Pending
		errMessage := fmt.Sprintf("prepareInstanceMountPoints error: %s", err.Error())
		d.containerStatus.Error = errMessage
		log.Println(errMessage)
		d.jobResult = JobResult{Reason: "EXECUTOR_ERROR", ReasonMessage: errMessage}
		return tracerr.Wrap(err)
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
		return tracerr.Wrap(err)
	}

	runnerDir, err := d.dockerParams.MakeRunnerDir()
	if err != nil {
		d.state = Pending
		errMessage := fmt.Sprintf("Cannot create dir for runner: %s", err.Error())
		d.containerStatus.Error = errMessage
		log.Print(errMessage + "\n")
		d.jobResult = JobResult{Reason: "CREATING_CONTAINER_ERROR", ReasonMessage: errMessage}
		return tracerr.Wrap(err)
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
		return tracerr.Wrap(err)
	}

	defer func() {
		log.Println("Deleting old container(s)")
		listFilters := filters.NewArgs(
			filters.Arg("label", fmt.Sprintf("%s=%s", LabelKeyIsRun, LabelValueTrue)),
			filters.Arg("status", "exited"),
		)
		containers, err := d.client.ContainerList(ctx, container.ListOptions{Filters: listFilters})
		if err != nil {
			log.Printf("ContainerList error: %s\n", err.Error())
			return
		}
		for _, container_ := range containers {
			if container_.ID == containerID {
				continue
			}
			err := d.client.ContainerRemove(ctx, container_.ID, container.RemoveOptions{Force: true, RemoveVolumes: true})
			if err != nil {
				log.Printf("ContainerRemove error: %s\n", err.Error())
			}
		}
	}()

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
		if errMessage == "" {
			lastLogs, err := getContainerLastLogs(d.client, containerID, 5)
			if err == nil {
				errMessage = strings.Join(lastLogs, "\n")
			} else {
				log.Printf("getContainerLastLogs error: %s\n", err.Error())
			}
		}
		d.jobResult = JobResult{Reason: "CONTAINER_EXITED_WITH_ERROR", ReasonMessage: errMessage}
		return tracerr.Wrap(err)
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

func (d *DockerRunner) GetState() (RunnerStatus, ContainerStatus, string, JobResult) {
	return d.state, d.containerStatus, d.executorError, d.jobResult
}

func getBackend(backendType string) (backends.Backend, error) {
	switch backendType {
	case "aws":
		return backends.NewAWSBackend(), nil
	case "gcp":
		return backends.NewGCPBackend(), nil
	}
	return nil, fmt.Errorf("unknown backend: %q", backendType)
}

func prepareVolumes(taskConfig TaskConfig) error {
	for _, volume := range taskConfig.Volumes {
		err := formatAndMountVolume(volume)
		if err != nil {
			return tracerr.Wrap(err)
		}
	}
	return nil
}

func unmountVolumes(taskConfig TaskConfig) error {
	if len(taskConfig.Volumes) == 0 {
		return nil
	}
	log.Println("Unmounting volumes...")
	var failed []string
	for _, volume := range taskConfig.Volumes {
		mountPoint := getVolumeMountPoint(volume.Name)
		cmd := exec.Command("mountpoint", mountPoint)
		if output, err := cmd.CombinedOutput(); err != nil {
			log.Printf("Skipping %s: %s", mountPoint, output)
			continue
		}
		cmd = exec.Command("umount", "-qf", mountPoint)
		if output, err := cmd.CombinedOutput(); err != nil {
			log.Printf("Failed to unmount %s: %s", mountPoint, output)
			failed = append(failed, mountPoint)
		} else {
			log.Printf("Unmounted: %s\n", mountPoint)
		}
	}
	if len(failed) > 0 {
		return fmt.Errorf("failed to unmount volume(s): %v", failed)
	}
	return nil
}

func formatAndMountVolume(volume VolumeInfo) error {
	backend, err := getBackend(volume.Backend)
	if err != nil {
		return tracerr.Wrap(err)
	}
	deviceName, err := backend.GetRealDeviceName(volume.VolumeId)
	if err != nil {
		return tracerr.Wrap(err)
	}
	_, err = initFileSystem(deviceName, !volume.InitFs)
	if err != nil {
		return tracerr.Wrap(err)
	}
	err = mountDisk(deviceName, getVolumeMountPoint(volume.Name))
	if err != nil {
		return tracerr.Wrap(err)
	}
	return nil
}

func getVolumeMountPoint(volumeName string) string {
	// Put volumes in data-specific dir to avoid clashes with host dirs
	return fmt.Sprintf("/dstack-volumes/%s", volumeName)
}

func prepareInstanceMountPoints(taskConfig TaskConfig) error {
	for _, mountPoint := range taskConfig.InstanceMounts {
		if _, err := os.Stat(mountPoint.InstancePath); errors.Is(err, os.ErrNotExist) {
			if err = os.MkdirAll(mountPoint.InstancePath, 0o777); err != nil {
				return tracerr.Wrap(err)
			}
		} else if err != nil {
			return tracerr.Wrap(err)
		}
	}
	return nil
}

// initFileSystem creates an ext4 file system on a disk only if the disk is not already has a file system.
// Returns true if the file system is created.
func initFileSystem(deviceName string, errorIfNotExists bool) (bool, error) {
	// Run the lsblk command to get filesystem type
	cmd := exec.Command("lsblk", "-no", "FSTYPE", deviceName)
	var out bytes.Buffer
	cmd.Stdout = &out
	if err := cmd.Run(); err != nil {
		return false, fmt.Errorf("failed to check if disk is formatted: %w", err)
	}

	// If the output is not empty, the disk is already formatted
	fsType := strings.TrimSpace(out.String())
	if fsType != "" {
		return false, nil
	}

	if errorIfNotExists {
		return false, fmt.Errorf("disk has no file system")
	}

	log.Printf("Formatting disk %s with ext4 filesystem...\n", deviceName)
	cmd = exec.Command("mkfs.ext4", "-F", deviceName)
	if output, err := cmd.CombinedOutput(); err != nil {
		return false, fmt.Errorf("failed to format disk: %w, output: %s", err, string(output))
	}
	log.Println("Disk formatted succesfully!")
	return true, nil
}

func mountDisk(deviceName, mountPoint string) error {
	// Create the mount point directory if it doesn't exist
	if _, err := os.Stat(mountPoint); os.IsNotExist(err) {
		fmt.Printf("Creating mount point %s...\n", mountPoint)
		if err := os.MkdirAll(mountPoint, 0o755); err != nil {
			return fmt.Errorf("failed to create mount point: %w", err)
		}
	}

	// Mount the disk to the mount point
	log.Printf("Mounting disk %s to %s...\n", deviceName, mountPoint)
	cmd := exec.Command("mount", deviceName, mountPoint)
	if output, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("failed to mount disk: %w, output: %s", err, string(output))
	}

	log.Println("Disk mounted successfully!")
	return nil
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
		Error          string         `json:"error"`
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
		if progressRow.Error != "" {
			log.Printf("Error pulling %s: %s", taskConfig.ImageName, progressRow.Error)
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

	removeOptions := container.RemoveOptions{Force: true, RemoveVolumes: true}
	err = client.ContainerRemove(ctx, taskConfig.ContainerName, removeOptions)
	if err != nil {
		log.Printf("Cleanup routine: Cannot remove container: %s", err)
	}

	mounts, err := dockerParams.DockerMounts(runnerDir)
	if err != nil {
		return "", tracerr.Wrap(err)
	}
	volumeMounts, err := getVolumeMounts(taskConfig.VolumeMounts)
	if err != nil {
		return "", tracerr.Wrap(err)
	}
	mounts = append(mounts, volumeMounts...)
	instanceMounts, err := getInstanceMounts(taskConfig.InstanceMounts)
	if err != nil {
		return "", tracerr.Wrap(err)
	}
	mounts = append(mounts, instanceMounts...)

	// Set the environment variables
	envVars := []string{}
	if dockerParams.DockerPJRTDevice() != "" {
		envVars = append(envVars, fmt.Sprintf("PJRT_DEVICE=%s", dockerParams.DockerPJRTDevice()))
	}

	// Override /dev/shm with tmpfs mount with `exec` option (the default is `noexec`)
	// if ShmSize is specified (i.e. not zero, which is the default value).
	// This is required by some workloads, e.g., Oracle Database with Java Stored Procedures,
	// see https://github.com/moby/moby/issues/6758
	var tmpfs map[string]string
	if taskConfig.ShmSize > 0 {
		// No need to specify all default options (`nosuid`, etc.),
		// the docker daemon will merge our options with the defaults.
		tmpfs = map[string]string{
			"/dev/shm": fmt.Sprintf("exec,size=%d", taskConfig.ShmSize),
		}
	}

	containerConfig := &container.Config{
		Image:        taskConfig.ImageName,
		Cmd:          []string{strings.Join(dockerParams.DockerShellCommands(taskConfig.PublicKeys), " && ")},
		Entrypoint:   []string{"/bin/sh", "-c"},
		ExposedPorts: exposePorts(dockerParams.DockerPorts()...),
		Env:          envVars,
		Labels: map[string]string{
			LabelKeyIsRun: LabelValueTrue,
		},
	}
	if taskConfig.ContainerUser != "" {
		containerConfig.User = taskConfig.ContainerUser
	}
	hostConfig := &container.HostConfig{
		Privileged:      taskConfig.Privileged || dockerParams.DockerPrivileged(),
		NetworkMode:     getNetworkMode(),
		PortBindings:    bindPorts(dockerParams.DockerPorts()...),
		PublishAllPorts: true,
		Sysctls:         map[string]string{},
		Mounts:          mounts,
		ShmSize:         taskConfig.ShmSize,
		Tmpfs:           tmpfs,
	}
	configureGpuIfAvailable(hostConfig)
	configureHpcNetworkingIfAvailable(hostConfig)

	log.Printf("Creating container %s:\nconfig: %v\nhostConfig:%v", taskConfig.ContainerName, containerConfig, hostConfig)
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
	case waitResp := <-waitCh:
		{
			if waitResp.StatusCode != 0 {
				return fmt.Errorf("container exited with exit code %d", waitResp.StatusCode)
			}
		}
	case err := <-errorCh:
		return tracerr.Wrap(err)
	}

	return nil
}

func getSSHShellCommands(openSSHPort int, publicSSHKey string) []string {
	return []string{
		// save and unset ld.so variables
		`_LD_LIBRARY_PATH=${LD_LIBRARY_PATH-} && unset LD_LIBRARY_PATH`,
		`_LD_PRELOAD=${LD_PRELOAD-} && unset LD_PRELOAD`,
		// common functions
		`_exists() { command -v "$1" > /dev/null 2>&1; }`,
		// TODO(#1535): support non-root images properly
		"mkdir -p /root && chown root:root /root && export HOME=/root",
		// package manager detection/abstraction
		`_install() { NAME=Distribution; test -f /etc/os-release && . /etc/os-release; echo $NAME not supported; exit 11; }`,
		`if _exists apt-get; then _install() { apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y "$1"; }; fi`,
		`if _exists yum; then _install() { yum install -y "$1"; }; fi`,
		// check in sshd is here, install if not
		`if ! _exists sshd; then _install openssh-server; fi`,
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
		// Ensure that PRIVSEP_PATH 1) exists 2) empty 3) owned by root,
		// see https://github.com/dstackai/dstack/issues/1999
		// /run/sshd is used in Debian-based distros, including Ubuntu:
		// https://salsa.debian.org/ssh-team/openssh/-/blob/debian/1%259.7p1-7/debian/rules#L60
		// /var/empty is the default path if not configured via ./configure --with-privsep-path=...
		"rm -rf /run/sshd && mkdir -p /run/sshd && chown root:root /run/sshd",
		"rm -rf /var/empty && mkdir -p /var/empty && chown root:root /var/empty",
		// start sshd
		fmt.Sprintf("/usr/sbin/sshd -p %d -o PermitUserEnvironment=yes", openSSHPort),
		// restore ld.so variables
		`if [ -n "$_LD_LIBRARY_PATH" ]; then export LD_LIBRARY_PATH="$_LD_LIBRARY_PATH"; fi`,
		`if [ -n "$_LD_PRELOAD" ]; then export LD_PRELOAD="$_LD_PRELOAD"; fi`,
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

func configureGpuIfAvailable(hostConfig *container.HostConfig) {
	switch gpuVendor := GetGpuVendor(); gpuVendor {
	case Nvidia:
		hostConfig.Resources.DeviceRequests = append(
			hostConfig.Resources.DeviceRequests,
			container.DeviceRequest{
				// Request all capabilities to maximize compatibility with all sorts of GPU workloads.
				// Default capabilities: utility, compute.
				// https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/1.16.0/docker-specialized.html
				Capabilities: [][]string{{"gpu", "utility", "compute", "graphics", "video", "display", "compat32"}},
				Count:        -1, // --gpus=all
			},
		)
	case Amd:
		// All options are listed here: https://hub.docker.com/r/rocm/pytorch
		// Only --device are mandatory, other seem to be performance-related.
		// --device=/dev/kfd --device=/dev/dri
		hostConfig.Resources.Devices = append(
			hostConfig.Resources.Devices,
			container.DeviceMapping{
				PathOnHost:        "/dev/kfd",
				PathInContainer:   "/dev/kfd",
				CgroupPermissions: "rwm",
			},
			container.DeviceMapping{
				PathOnHost:        "/dev/dri",
				PathInContainer:   "/dev/dri",
				CgroupPermissions: "rwm",
			},
		)
		// --ipc=host
		hostConfig.IpcMode = container.IPCModeHost
		// --cap-add=SYS_PTRACE
		hostConfig.CapAdd = append(hostConfig.CapAdd, "SYS_PTRACE")
		// --security-opt=seccomp=unconfined
		hostConfig.SecurityOpt = append(hostConfig.SecurityOpt, "seccomp=unconfined")
		// TODO: in addition, for non-root user, --group-add=video, and possibly --group-add=render, are required.
	case NoVendor:
		// nothing to do
	}
}

func configureHpcNetworkingIfAvailable(hostConfig *container.HostConfig) {
	// Although AWS EFA is not InfiniBand, EFA adapters are exposed as /dev/infiniband/uverbsN (N=0,1,...)
	if _, err := os.Stat("/dev/infiniband"); !errors.Is(err, os.ErrNotExist) {
		hostConfig.Resources.Devices = append(
			hostConfig.Resources.Devices,
			container.DeviceMapping{
				PathOnHost:        "/dev/infiniband",
				PathInContainer:   "/dev/infiniband",
				CgroupPermissions: "rwm",
			},
		)
		// Set max locked memory (ulimit -l) to unlimited. Fixes "Libfabric error: (-12) Cannot allocate memory".
		// See: https://github.com/ofiwg/libfabric/issues/6437
		// See: https://aws.amazon.com/blogs/compute/leveraging-efa-to-run-hpc-and-ml-workloads-on-aws-batch/
		hostConfig.Ulimits = append(
			hostConfig.Ulimits,
			&units.Ulimit{
				Name: "memlock",
				Soft: -1,
				Hard: -1,
			},
		)
	}
}

func getVolumeMounts(mountPoints []VolumeMountPoint) ([]mount.Mount, error) {
	mounts := []mount.Mount{}
	for _, mountPoint := range mountPoints {
		source := getVolumeMountPoint(mountPoint.Name)
		mounts = append(mounts, mount.Mount{Type: mount.TypeBind, Source: source, Target: mountPoint.Path})
	}
	return mounts, nil
}

func getInstanceMounts(mountPoints []InstanceMountPoint) ([]mount.Mount, error) {
	mounts := []mount.Mount{}
	for _, mountPoint := range mountPoints {
		mounts = append(mounts, mount.Mount{Type: mount.TypeBind, Source: mountPoint.InstancePath, Target: mountPoint.Path})
	}
	return mounts, nil
}

func getContainerLastLogs(client docker.APIClient, containerID string, n int) ([]string, error) {
	options := container.LogsOptions{
		ShowStdout: true,
		ShowStderr: true,
		Tail:       fmt.Sprintf("%d", n),
	}

	ctx := context.Background()
	muxedReader, err := client.ContainerLogs(ctx, containerID, options)
	if err != nil {
		return nil, err
	}
	defer muxedReader.Close()

	demuxedBuffer := new(bytes.Buffer)
	// Using the same Writer for both stdout and stderr should be roughly equivalent to 2>&1
	if _, err := stdcopy.StdCopy(demuxedBuffer, demuxedBuffer, muxedReader); err != nil {
		return nil, err
	}

	var lines []string
	scanner := bufio.NewScanner(demuxedBuffer)
	for scanner.Scan() {
		lines = append(lines, scanner.Text())
	}
	if err := scanner.Err(); err != nil && !errors.Is(err, io.EOF) {
		return nil, err
	}

	return lines, nil
}

/* DockerParameters interface implementation for CLIArgs */

func (c *CLIArgs) DockerPrivileged() bool {
	return c.Docker.Privileged
}

func (c *CLIArgs) DockerPJRTDevice() string {
	return c.Docker.PJRTDevice
}

func (c *CLIArgs) DockerShellCommands(publicKeys []string) []string {
	concatinatedPublicKeys := c.Docker.ConcatinatedPublicSSHKeys
	if len(publicKeys) > 0 {
		concatinatedPublicKeys = strings.Join(publicKeys, "\n")
	}
	commands := getSSHShellCommands(c.Docker.SSHPort, concatinatedPublicKeys)
	commands = append(commands, fmt.Sprintf("%s %s", DstackRunnerBinaryName, strings.Join(c.getRunnerArgs(), " ")))
	return commands
}

func (c *CLIArgs) DockerMounts(hostRunnerDir string) ([]mount.Mount, error) {
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

func (c *CLIArgs) DockerPorts() []int {
	return []int{c.Runner.HTTPPort, c.Docker.SSHPort}
}

func (c *CLIArgs) MakeRunnerDir() (string, error) {
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
			if errors.Is(err, io.EOF) {
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
