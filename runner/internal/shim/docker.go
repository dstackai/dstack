package shim

import (
	"bufio"
	"bytes"
	"context"
	"encoding/base64"
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
	"github.com/docker/docker/api/types/registry"
	dockersystem "github.com/docker/docker/api/types/system"
	docker "github.com/docker/docker/client"
	"github.com/docker/docker/pkg/stdcopy"
	"github.com/docker/go-connections/nat"
	"github.com/docker/go-units"
	"github.com/dstackai/dstack/runner/internal/shim/backends"
	"github.com/dstackai/dstack/runner/internal/shim/host"
	bytesize "github.com/inhies/go-bytesize"
	"github.com/ztrue/tracerr"
)

// TODO: Allow for configuration via cli arguments or environment variables.
const ImagePullTimeout time.Duration = 20 * time.Minute

const (
	LabelKeyPrefix = "ai.dstack.shim."
	// Set to "true" on containers spawned by DockerRunner, used for identification.
	LabelKeyIsTask = LabelKeyPrefix + "is-task"
	LabelKeyTaskID = LabelKeyPrefix + "task-id"
	LabelValueTrue = "true"
)

type JobResult struct {
	Reason        string `json:"reason"`
	ReasonMessage string `json:"reason_message"`
}

type DockerRunner struct {
	client       *docker.Client
	dockerParams DockerParameters
	dockerInfo   dockersystem.Info
	gpus         []host.GpuInfo
	gpuVendor    host.GpuVendor
	gpuLock      *GpuLock
	tasks        TaskStorage
}

func NewDockerRunner(dockerParams DockerParameters) (*DockerRunner, error) {
	client, err := docker.NewClientWithOpts(docker.FromEnv, docker.WithAPIVersionNegotiation())
	if err != nil {
		return nil, tracerr.Wrap(err)
	}
	dockerInfo, err := client.Info(context.TODO())
	if err != nil {
		return nil, tracerr.Wrap(err)
	}

	var gpuVendor host.GpuVendor
	gpus := host.GetGpuInfo()
	if len(gpus) > 0 {
		gpuVendor = gpus[0].Vendor
	} else {
		gpuVendor = host.GpuVendorNone
	}
	gpuLock, err := NewGpuLock(gpus)
	if err != nil {
		return nil, tracerr.Wrap(err)
	}

	runner := &DockerRunner{
		client:       client,
		dockerParams: dockerParams,
		dockerInfo:   dockerInfo,
		gpus:         gpus,
		gpuVendor:    gpuVendor,
		gpuLock:      gpuLock,
		tasks:        NewTaskStorage(),
	}
	return runner, nil
}

func (d *DockerRunner) Resources() Resources {
	cpuCount := host.GetCpuCount()
	totalMemory, err := host.GetTotalMemory()
	if err != nil {
		log.Println(err)
	}
	netAddresses, err := host.GetNetworkAddresses()
	if err != nil {
		log.Println(err)
	}
	diskSize, err := host.GetDiskSize(d.dockerInfo.DockerRootDir)
	if err != nil {
		log.Println(err)
	}
	return Resources{
		Gpus:         d.gpus,
		CpuCount:     cpuCount,
		TotalMemory:  totalMemory,
		DiskSize:     diskSize,
		NetAddresses: netAddresses,
	}
}

func (d *DockerRunner) Run(ctx context.Context, cfg TaskConfig) error {
	task := NewTask(cfg)

	// For legacy API compatibility, since LegacyTaskID is the same for all tasks
	if task.ID == LegacyTaskID {
		d.tasks.Delete(task.ID)
	}

	if ok := d.tasks.Add(task); !ok {
		return tracerr.Errorf("task %s is already submitted", task.ID)
	}

	defer func() {
		if ok := d.tasks.Update(task); !ok {
			log.Printf("failed to update task %s", task.ID)
		}
	}()

	var err error

	if cfg.GpuCount != 0 {
		gpuIDs, err := d.gpuLock.Acquire(cfg.GpuCount)
		if err != nil {
			log.Println(err)
			task.SetStatusTerminated("EXECUTOR_ERROR", err.Error())
			return tracerr.Wrap(err)
		}
		task.gpuIDs = gpuIDs

		defer func() {
			d.gpuLock.Release(task.gpuIDs)
		}()
	}

	if cfg.SshKey != "" {
		ak := AuthorizedKeys{user: cfg.SshUser, lookup: user.Lookup}
		if err := ak.AppendPublicKeys([]string{cfg.SshKey}); err != nil {
			errMessage := fmt.Sprintf("ak.AppendPublicKeys error: %s", err.Error())
			log.Println(errMessage)
			task.SetStatusTerminated("EXECUTOR_ERROR", errMessage)
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
		errMessage := fmt.Sprintf("prepareVolumes error: %s", err.Error())
		log.Println(errMessage)
		task.SetStatusTerminated("EXECUTOR_ERROR", errMessage)
		return tracerr.Wrap(err)
	}
	err = prepareInstanceMountPoints(cfg)
	if err != nil {
		errMessage := fmt.Sprintf("prepareInstanceMountPoints error: %s", err.Error())
		log.Println(errMessage)
		task.SetStatusTerminated("EXECUTOR_ERROR", errMessage)
		return tracerr.Wrap(err)
	}

	log.Println("Pulling image")
	pullCtx, cancelPull := context.WithTimeout(ctx, ImagePullTimeout)
	defer cancelPull()
	task.SetStatusPulling(cancelPull)
	if !d.tasks.Update(task) {
		return tracerr.Errorf("failed to update task %s", task.ID)
	}
	if err = pullImage(pullCtx, d.client, cfg); err != nil {
		errMessage := fmt.Sprintf("pullImage error: %s", err.Error())
		log.Print(errMessage + "\n")
		task.SetStatusTerminated("CREATING_CONTAINER_ERROR", errMessage)
		return tracerr.Wrap(err)
	}

	log.Println("Creating container")
	task.SetStatusCreating()
	if !d.tasks.Update(task) {
		return tracerr.Errorf("failed to update task %s", task.ID)
	}
	containerID, err := d.createContainer(ctx, task)
	if err != nil {
		errMessage := fmt.Sprintf("createContainer error: %s", err.Error())
		log.Print(errMessage + "\n")
		task.SetStatusTerminated("CREATING_CONTAINER_ERROR", errMessage)
		return tracerr.Wrap(err)
	}

	defer func() {
		log.Println("Deleting old container(s)")
		listFilters := filters.NewArgs(
			filters.Arg("label", fmt.Sprintf("%s=%s", LabelKeyIsTask, LabelValueTrue)),
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

	log.Printf("Running container, name=%s, id=%s\n", task.containerName, containerID)
	task.SetStatusRunning(containerID)
	if !d.tasks.Update(task) {
		return tracerr.Errorf("failed to update task %s", task.ID)
	}

	if err = runContainer(ctx, d.client, containerID); err != nil {
		log.Printf("runContainer error: %s\n", err.Error())
		var errMessage string
		if lastLogs, err := getContainerLastLogs(d.client, containerID, 5); err == nil {
			errMessage = strings.Join(lastLogs, "\n")
		} else {
			log.Printf("getContainerLastLogs error: %s\n", err.Error())
			errMessage = ""
		}
		task.SetStatusTerminated("CONTAINER_EXITED_WITH_ERROR", errMessage)
		return tracerr.Wrap(err)
	}

	log.Printf("Container finished successfully, name=%s, id=%s", task.containerName, containerID)
	task.SetStatusTerminated("DONE_BY_RUNNER", "")

	return nil
}

func (d *DockerRunner) Stop(force bool) {
	task, ok := d.tasks.Get(LegacyTaskID)
	if !ok {
		return
	}
	switch task.Status {
	case TaskStatusPending, TaskStatusCreating, TaskStatusTerminated:
		// nothing to do
	case TaskStatusPulling:
		task.cancelPull()
	case TaskStatusRunning:
		stopOptions := container.StopOptions{}
		if force {
			timeout := int(0)
			stopOptions.Timeout = &timeout
		}
		err := d.client.ContainerStop(context.Background(), task.containerID, stopOptions)
		if err != nil {
			log.Printf("Failed to stop container: %s", err)
		}
	}
}

func (d *DockerRunner) GetState() (RunnerStatus, JobResult) {
	if task, ok := d.tasks.Get(LegacyTaskID); ok {
		return getLegacyStatus(task), JobResult{
			Reason:        task.TerminationReason,
			ReasonMessage: task.TerminationMessage,
		}
	}
	return Pending, JobResult{}
}

func getLegacyStatus(task Task) RunnerStatus {
	switch task.Status {
	case TaskStatusPending:
		return Pulling
	case TaskStatusPulling:
		return Pulling
	case TaskStatusCreating:
		return Creating
	case TaskStatusRunning:
		return Running
	case TaskStatusTerminated:
		return Pending
	}
	// should not reach here
	return ""
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
	deviceName, err := backend.GetRealDeviceName(volume.VolumeId, volume.DeviceName)
	if err != nil {
		return tracerr.Wrap(err)
	}
	fsCreated, err := initFileSystem(deviceName, !volume.InitFs)
	if err != nil {
		return tracerr.Wrap(err)
	}
	// Make FS root directory world-writable (0777) to give any job user
	// a permission to create new files
	// NOTE: mke2fs (that is, mkfs.ext4) supports `-E root_perms=0777` since 1.47.1:
	// https://e2fsprogs.sourceforge.net/e2fsprogs-release.html#1.47.1
	// but, as of 2024-12-04, this version is too new to rely on, for example,
	// Ubuntu 24.04 LTS has only 1.47.0
	// 0 means "do not chmod root directory"
	var fsRootPerms os.FileMode = 0
	// Change permissions only if the FS was created by us, don't mess with
	// user-formatted volumes
	if fsCreated {
		fsRootPerms = 0o777
	}
	err = mountDisk(deviceName, getVolumeMountPoint(volume.Name), fsRootPerms)
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
	// If the instance volume directory doesn't exist, create it with world-writable permissions (0777)
	// to give any job user a permission to create new files
	// If the directory already exists, do nothing, don't mess with already set permissions, especially
	// on SSH fleets where permissions are managed by the host admin
	for _, mountPoint := range taskConfig.InstanceMounts {
		if _, err := os.Stat(mountPoint.InstancePath); errors.Is(err, os.ErrNotExist) {
			// All missing parent dirs are created with 0755 permissions
			if err = os.MkdirAll(mountPoint.InstancePath, 0o755); err != nil {
				return tracerr.Wrap(err)
			}
			if err = os.Chmod(mountPoint.InstancePath, 0o777); err != nil {
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

func mountDisk(deviceName, mountPoint string, fsRootPerms os.FileMode) error {
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

	if fsRootPerms != 0 {
		if err := os.Chmod(mountPoint, fsRootPerms); err != nil {
			return fmt.Errorf("failed to chmod volume root directory %s: %w", mountPoint, err)
		}
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
	regAuth, _ := encodeRegistryAuth(taskConfig.RegistryUsername, taskConfig.RegistryPassword)
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

func (d *DockerRunner) createContainer(ctx context.Context, task Task) (string, error) {
	// For legacy API compatibility, since LegacyTaskID is the same for all tasks, containerName is not unique
	// With new API where task.ID is unique (and, in turn, containerName is unique too), container name clash
	// is not expected
	if task.ID == LegacyTaskID {
		timeout := int(0)
		stopOptions := container.StopOptions{Timeout: &timeout}
		err := d.client.ContainerStop(ctx, task.containerName, stopOptions)
		if err != nil {
			log.Printf("Cleanup routine: Cannot stop container: %s", err)
		}
		removeOptions := container.RemoveOptions{Force: true, RemoveVolumes: true}
		err = d.client.ContainerRemove(ctx, task.containerName, removeOptions)
		if err != nil {
			log.Printf("Cleanup routine: Cannot remove container: %s", err)
		}
	}

	runnerDir, err := d.dockerParams.MakeRunnerDir()
	if err != nil {
		return "", tracerr.Wrap(err)
	}
	mounts, err := d.dockerParams.DockerMounts(runnerDir)
	if err != nil {
		return "", tracerr.Wrap(err)
	}
	volumeMounts, err := getVolumeMounts(task.config.VolumeMounts)
	if err != nil {
		return "", tracerr.Wrap(err)
	}
	mounts = append(mounts, volumeMounts...)
	instanceMounts, err := getInstanceMounts(task.config.InstanceMounts)
	if err != nil {
		return "", tracerr.Wrap(err)
	}
	mounts = append(mounts, instanceMounts...)

	// Set the environment variables
	envVars := []string{}
	if d.dockerParams.DockerPJRTDevice() != "" {
		envVars = append(envVars, fmt.Sprintf("PJRT_DEVICE=%s", d.dockerParams.DockerPJRTDevice()))
	}

	// Override /dev/shm with tmpfs mount with `exec` option (the default is `noexec`)
	// if ShmSize is specified (i.e. not zero, which is the default value).
	// This is required by some workloads, e.g., Oracle Database with Java Stored Procedures,
	// see https://github.com/moby/moby/issues/6758
	var tmpfs map[string]string
	if task.config.ShmSize > 0 {
		// No need to specify all default options (`nosuid`, etc.),
		// the docker daemon will merge our options with the defaults.
		tmpfs = map[string]string{
			"/dev/shm": fmt.Sprintf("exec,size=%d", task.config.ShmSize),
		}
	}

	containerConfig := &container.Config{
		Image:        task.config.ImageName,
		Cmd:          []string{strings.Join(d.dockerParams.DockerShellCommands(task.config.PublicKeys), " && ")},
		Entrypoint:   []string{"/bin/sh", "-c"},
		ExposedPorts: exposePorts(d.dockerParams.DockerPorts()...),
		Env:          envVars,
		Labels: map[string]string{
			LabelKeyIsTask: LabelValueTrue,
			LabelKeyTaskID: task.ID,
		},
	}
	if task.config.ContainerUser != "" {
		containerConfig.User = task.config.ContainerUser
	}
	hostConfig := &container.HostConfig{
		Privileged:      task.config.Privileged || d.dockerParams.DockerPrivileged(),
		NetworkMode:     getNetworkMode(),
		PortBindings:    bindPorts(d.dockerParams.DockerPorts()...),
		PublishAllPorts: true,
		Sysctls:         map[string]string{},
		Mounts:          mounts,
		ShmSize:         task.config.ShmSize,
		Tmpfs:           tmpfs,
	}
	if len(task.gpuIDs) > 0 {
		configureGpus(hostConfig, d.gpuVendor, task.gpuIDs)
	}
	configureHpcNetworkingIfAvailable(hostConfig)

	log.Printf("Creating container %s:\nconfig: %v\nhostConfig:%v", task.containerName, containerConfig, hostConfig)
	resp, err := d.client.ContainerCreate(ctx, containerConfig, hostConfig, nil, nil, task.containerName)
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

func encodeRegistryAuth(username string, password string) (string, error) {
	if username == "" && password == "" {
		return "", nil
	}

	authConfig := registry.AuthConfig{
		Username: username,
		Password: password,
	}

	encodedConfig, err := json.Marshal(authConfig)
	if err != nil {
		log.Println("Failed to encode auth config", "err", err)
		return "", err
	}

	return base64.URLEncoding.EncodeToString(encodedConfig), nil
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
		"mkdir -p ~/.ssh",
		"chmod 700 ~/.ssh",
		fmt.Sprintf("echo '%s' > ~/.ssh/authorized_keys", publicSSHKey),
		"chmod 600 ~/.ssh/authorized_keys",
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

func configureGpus(hostConfig *container.HostConfig, vendor host.GpuVendor, ids []string) {
	// NVIDIA: ids are identifiers reported by nvidia-smi, GPU-<UUID> strings
	// AMD: ids are DRI render node paths, e.g., /dev/dri/renderD128
	switch vendor {
	case host.GpuVendorNvidia:
		hostConfig.Resources.DeviceRequests = append(
			hostConfig.Resources.DeviceRequests,
			container.DeviceRequest{
				// Request all capabilities to maximize compatibility with all sorts of GPU workloads.
				// Default capabilities: utility, compute.
				// https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/1.16.0/docker-specialized.html
				Capabilities: [][]string{{"gpu", "utility", "compute", "graphics", "video", "display", "compat32"}},
				DeviceIDs:    ids,
			},
		)
	case host.GpuVendorAmd:
		// All options are listed here: https://hub.docker.com/r/rocm/pytorch
		// Only --device are mandatory, other seem to be performance-related.
		// --device=/dev/kfd
		hostConfig.Resources.Devices = append(
			hostConfig.Resources.Devices,
			container.DeviceMapping{
				PathOnHost:        "/dev/kfd",
				PathInContainer:   "/dev/kfd",
				CgroupPermissions: "rwm",
			},
		)
		// --device=/dev/renderD<N>
		for _, renderNodePath := range ids {
			hostConfig.Resources.Devices = append(
				hostConfig.Resources.Devices,
				container.DeviceMapping{
					PathOnHost:        renderNodePath,
					PathInContainer:   renderNodePath,
					CgroupPermissions: "rwm",
				},
			)
		}
		// --ipc=host
		hostConfig.IpcMode = container.IPCModeHost
		// --cap-add=SYS_PTRACE
		hostConfig.CapAdd = append(hostConfig.CapAdd, "SYS_PTRACE")
		// --security-opt=seccomp=unconfined
		hostConfig.SecurityOpt = append(hostConfig.SecurityOpt, "seccomp=unconfined")
		// TODO: in addition, for non-root user, --group-add=video, and possibly --group-add=render, are required.
	case host.GpuVendorNone:
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
