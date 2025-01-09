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
	"github.com/docker/docker/errdefs"
	"github.com/docker/docker/pkg/stdcopy"
	"github.com/docker/go-connections/nat"
	"github.com/docker/go-units"
	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/log"
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

type DockerRunner struct {
	client       *docker.Client
	dockerParams DockerParameters
	dockerInfo   dockersystem.Info
	gpus         []host.GpuInfo
	gpuVendor    host.GpuVendor
	gpuLock      *GpuLock
	tasks        TaskStorage
}

func NewDockerRunner(ctx context.Context, dockerParams DockerParameters) (*DockerRunner, error) {
	client, err := docker.NewClientWithOpts(docker.FromEnv, docker.WithAPIVersionNegotiation())
	if err != nil {
		return nil, tracerr.Wrap(err)
	}
	dockerInfo, err := client.Info(ctx)
	if err != nil {
		return nil, tracerr.Wrap(err)
	}

	var gpuVendor host.GpuVendor
	gpus := host.GetGpuInfo(ctx)
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

	if err := runner.restoreStateFromContainers(ctx); err != nil {
		return nil, tracerr.Errorf("failed to restore state from containers: %w", err)
	}

	return runner, nil
}

// restoreStateFromContainers regenerates TaskStorage and GpuLock inspecting containers
// Used to restore shim state on restarts
func (d *DockerRunner) restoreStateFromContainers(ctx context.Context) error {
	listOptions := container.ListOptions{
		All:     true,
		Filters: filters.NewArgs(filters.Arg("label", fmt.Sprintf("%s=%s", LabelKeyIsTask, LabelValueTrue))),
	}
	containers, err := d.client.ContainerList(ctx, listOptions)
	if err != nil {
		return fmt.Errorf("failed to get container list: %w", err)
	}
	for _, containerShort := range containers {
		containerID := containerShort.ID
		taskID := containerShort.Labels[LabelKeyTaskID]
		if taskID == "" {
			log.Error(ctx, "container has no label", "id", containerID, "label", LabelKeyTaskID)
			continue
		}
		var status TaskStatus
		if containerShort.State == "exited" {
			status = TaskStatusTerminated
		} else {
			status = TaskStatusRunning
		}
		var containerName string
		if len(containerShort.Names) > 0 {
			// "Names are prefixed with their parent and / == the docker daemon"
			// https://github.com/moby/moby/issues/6705
			containerName = strings.TrimLeft(containerShort.Names[0], "/")
		}
		var gpuIDs []string
		if d.gpuVendor != host.GpuVendorNone {
			if containerFull, err := d.client.ContainerInspect(ctx, containerID); err != nil {
				log.Error(ctx, "failed to inspect container", "id", containerID, "task", taskID)
			} else if d.gpuVendor == host.GpuVendorNvidia {
				deviceRequests := containerFull.HostConfig.Resources.DeviceRequests
				if len(deviceRequests) == 1 {
					gpuIDs = deviceRequests[0].DeviceIDs
				} else if len(deviceRequests) != 0 {
					log.Error(
						ctx,
						"cannot extract GPU IDs from container: more than one DeviceRequest",
						"id", containerID, "task", taskID,
					)
				}
			} else {
				for _, device := range containerFull.HostConfig.Resources.Devices {
					if host.IsRenderNodePath(device.PathOnHost) {
						gpuIDs = append(gpuIDs, device.PathOnHost)
					}
				}
			}
		}
		var runnerDir string
		for _, mount := range containerShort.Mounts {
			if mount.Destination == consts.RunnerTempDir {
				runnerDir = mount.Source
				break
			}
		}
		task := NewTask(taskID, status, containerName, containerID, gpuIDs, runnerDir)
		if !d.tasks.Add(task) {
			log.Error(ctx, "duplicate restored task", "task", taskID)
		} else {
			log.Debug(ctx, "restored task", "task", taskID, "status", status, "gpus", gpuIDs)
		}
		if status == TaskStatusRunning && len(gpuIDs) > 0 {
			lockedGpuIDs := d.gpuLock.Lock(ctx, gpuIDs)
			log.Debug(ctx, "locked GPU(s) due to running task", "task", taskID, "gpus", lockedGpuIDs)
		}
	}
	return nil
}

func (d *DockerRunner) Resources(ctx context.Context) Resources {
	cpuCount := host.GetCpuCount(ctx)
	totalMemory, err := host.GetTotalMemory(ctx)
	if err != nil {
		log.Error(ctx, err.Error())
	}
	netAddresses, err := host.GetNetworkAddresses(ctx)
	if err != nil {
		log.Error(ctx, err.Error())
	}
	diskSize, err := host.GetDiskSize(ctx, d.dockerInfo.DockerRootDir)
	if err != nil {
		log.Error(ctx, err.Error())
	}
	return Resources{
		Gpus:         d.gpus,
		CpuCount:     cpuCount,
		TotalMemory:  totalMemory,
		DiskSize:     diskSize,
		NetAddresses: netAddresses,
	}
}

func (d *DockerRunner) TaskIDs() []string {
	return d.tasks.IDs()
}

func (d *DockerRunner) TaskInfo(taskID string) TaskInfo {
	task, ok := d.tasks.Get(taskID)
	if !ok {
		return TaskInfo{}
	}
	taskInfo := TaskInfo{
		ID:                 task.ID,
		Status:             task.Status,
		TerminationReason:  task.TerminationReason,
		TerminationMessage: task.TerminationMessage,
		ContainerName:      task.containerName,
		ContainerID:        task.containerID,
		GpuIDs:             task.gpuIDs,
	}
	if taskInfo.GpuIDs == nil {
		taskInfo.GpuIDs = []string{}
	}
	return taskInfo
}

func (d *DockerRunner) Submit(ctx context.Context, cfg TaskConfig) error {
	if cfg.ID == "" {
		return tracerr.Errorf("%w: empty task ID", ErrRequest)
	}
	if cfg.Name == "" {
		return tracerr.Errorf("%w: empty task Name", ErrRequest)
	}
	task := NewTaskFromConfig(cfg)
	if ok := d.tasks.Add(task); !ok {
		return tracerr.Errorf("%w: task %s is already submitted", ErrRequest, task.ID)
	}
	log.Debug(ctx, "new task submitted", "task", task.ID)
	return nil
}

func (d *DockerRunner) Run(ctx context.Context, taskID string) error {
	task, ok := d.tasks.Get(taskID)
	if !ok {
		log.Error(ctx, "cannot run: not found", "task", taskID)
		return fmt.Errorf("task %s: %w", taskID, ErrNotFound)
	}

	if task.Status != TaskStatusPending {
		return fmt.Errorf("%w: cannot run task %s with %s status", ErrRequest, task.ID, task.Status)
	}

	defer func() {
		if err := d.tasks.Update(task); err != nil {
			if currentTask, ok := d.tasks.Get(task.ID); ok && currentTask.Status != task.Status {
				// ignore error if task is gone or status has not changed, e.g., terminated -> terminated
				log.Error(ctx, "failed to update", "task", task.ID, "err", err)
			}
		}
	}()

	task.SetStatusPreparing()
	if err := d.tasks.Update(task); err != nil {
		return tracerr.Errorf("%w: failed to update task %s: %w", ErrInternal, task.ID, err)
	}

	cfg := task.config
	var err error

	if cfg.GPU != 0 {
		gpuIDs, err := d.gpuLock.Acquire(ctx, cfg.GPU)
		if err != nil {
			log.Error(ctx, err.Error())
			task.SetStatusTerminated("EXECUTOR_ERROR", err.Error())
			return tracerr.Wrap(err)
		}
		task.gpuIDs = gpuIDs
		log.Debug(ctx, "acquired GPU(s)", "task", task.ID, "gpus", gpuIDs)

		defer func() {
			releasedGpuIDs := d.gpuLock.Release(ctx, task.gpuIDs)
			log.Debug(ctx, "released GPU(s)", "task", task.ID, "gpus", releasedGpuIDs)
		}()
	}

	if len(cfg.HostSshKeys) > 0 {
		ak := AuthorizedKeys{user: cfg.HostSshUser, lookup: user.Lookup}
		if err := ak.AppendPublicKeys(cfg.HostSshKeys); err != nil {
			errMessage := fmt.Sprintf("ak.AppendPublicKeys error: %s", err.Error())
			log.Error(ctx, errMessage)
			task.SetStatusTerminated("EXECUTOR_ERROR", errMessage)
			return tracerr.Wrap(err)
		}
		defer func(cfg TaskConfig) {
			err := ak.RemovePublicKeys(cfg.HostSshKeys)
			if err != nil {
				log.Error(ctx, "Error RemovePublicKeys", "err", err)
			}
		}(cfg)
	}

	log.Debug(ctx, "Preparing volumes")
	// defer unmountVolumes() before calling prepareVolumes(), as the latter
	// may fail when some volumes are already mounted; if the volume is not mounted,
	// unmountVolumes() simply skips it
	defer func() { _ = unmountVolumes(ctx, cfg) }()
	err = prepareVolumes(ctx, cfg)
	if err != nil {
		errMessage := fmt.Sprintf("prepareVolumes error: %s", err.Error())
		log.Error(ctx, errMessage)
		task.SetStatusTerminated("EXECUTOR_ERROR", errMessage)
		return tracerr.Wrap(err)
	}
	err = prepareInstanceMountPoints(cfg)
	if err != nil {
		errMessage := fmt.Sprintf("prepareInstanceMountPoints error: %s", err.Error())
		log.Error(ctx, errMessage)
		task.SetStatusTerminated("EXECUTOR_ERROR", errMessage)
		return tracerr.Wrap(err)
	}

	log.Debug(ctx, "Pulling image")
	pullCtx, cancelPull := context.WithTimeout(ctx, ImagePullTimeout)
	defer cancelPull()
	task.SetStatusPulling(cancelPull)
	if err := d.tasks.Update(task); err != nil {
		return tracerr.Errorf("%w: failed to update task %s: %w", ErrInternal, task.ID, err)
	}
	if err = pullImage(pullCtx, d.client, cfg); err != nil {
		errMessage := fmt.Sprintf("pullImage error: %s", err.Error())
		log.Error(ctx, errMessage)
		task.SetStatusTerminated("CREATING_CONTAINER_ERROR", errMessage)
		return tracerr.Wrap(err)
	}

	log.Debug(ctx, "Creating container", "task", task.ID, "name", task.containerName)
	task.SetStatusCreating()
	if err := d.tasks.Update(task); err != nil {
		return tracerr.Errorf("%w: failed to update task %s: %w", ErrInternal, task.ID, err)
	}
	containerID, err := d.createContainer(ctx, &task)
	if err != nil {
		errMessage := fmt.Sprintf("createContainer error: %s", err.Error())
		log.Error(ctx, errMessage)
		task.SetStatusTerminated("CREATING_CONTAINER_ERROR", errMessage)
		return tracerr.Wrap(err)
	}

	log.Debug(ctx, "Running container", "task", task.ID, "name", task.containerName)
	task.SetStatusRunning(containerID)
	if err := d.tasks.Update(task); err != nil {
		return tracerr.Errorf("%w: failed to update task %s: %w", ErrInternal, task.ID, err)
	}
	if err = d.runContainer(ctx, &task); err != nil {
		log.Error(ctx, "runContainer error", "err", err)
		var errMessage string
		if lastLogs, err := getContainerLastLogs(ctx, d.client, containerID, 5); err == nil {
			errMessage = strings.Join(lastLogs, "\n")
		} else {
			log.Error(ctx, "getContainerLastLogs error", "err", err)
			errMessage = ""
		}
		task.SetStatusTerminated("CONTAINER_EXITED_WITH_ERROR", errMessage)
		return tracerr.Wrap(err)
	}

	log.Debug(ctx, "Container finished successfully", "task", task.ID, "name", task.containerName)
	task.SetStatusTerminated("DONE_BY_RUNNER", "")

	return nil
}

// Terminate aborts running operations (pulling an image, running a container) and sets task status to terminated
// Associated resources (container, logs, etc.) are not destroyed, use Remove() for cleanup
func (d *DockerRunner) Terminate(ctx context.Context, taskID string, timeout uint, reason string, message string) (err error) {
	task, ok := d.tasks.Get(taskID)
	if !ok {
		log.Error(ctx, "cannot terminate task: not found", "task", taskID)
		return fmt.Errorf("task %s: %w", taskID, ErrNotFound)
	}
	task.Lock(ctx)
	defer func() { task.Release(ctx) }()
	defer func() {
		if err := d.tasks.Update(task); err != nil {
			log.Error(ctx, "failed to update task", "task", task.ID, "err", err)
		}
	}()
	return d.terminate(ctx, &task, timeout, reason, message)
}

func (d *DockerRunner) terminate(ctx context.Context, task *Task, timeout uint, reason string, message string) (err error) {
	log.Debug(ctx, "terminating", "task", task.ID)
	defer func() {
		if err != nil {
			log.Error(ctx, "cannot terminate task", "task", task.ID, "err", err)
		}
	}()
	if !task.IsTransitionAllowed(TaskStatusTerminated) {
		return fmt.Errorf("%w: cannot terminate task %s with %s status", ErrRequest, task.ID, task.Status)
	}
	switch task.Status {
	case TaskStatusPending, TaskStatusPreparing, TaskStatusCreating, TaskStatusTerminated:
		// nothing to do
	case TaskStatusPulling:
		task.cancelPull()
	case TaskStatusRunning:
		stopOptions := container.StopOptions{}
		timeout := int(timeout)
		stopOptions.Timeout = &timeout
		if err := d.client.ContainerStop(ctx, task.containerID, stopOptions); err != nil {
			return fmt.Errorf("%w: failed to stop container: %w", ErrInternal, err)
		}
	default:
		return fmt.Errorf("%w: should not reach here", ErrInternal)
	}
	if len(task.gpuIDs) > 0 {
		releasedGpuIDs := d.gpuLock.Release(ctx, task.gpuIDs)
		log.Debug(ctx, "released GPU(s)", "task", task.ID, "gpus", releasedGpuIDs)
	}
	task.SetStatusTerminated(reason, message)
	log.Debug(ctx, "terminated", "task", task.ID)
	return nil
}

// Remove destroys resources associated with task (container, logs, etc.), if any
// On success, it also removes the task from TaskStorage
func (d *DockerRunner) Remove(ctx context.Context, taskID string) error {
	task, ok := d.tasks.Get(taskID)
	if !ok {
		log.Error(ctx, "cannot remove: not found", "task", taskID)
		return fmt.Errorf("task %s: %w", taskID, ErrNotFound)
	}
	task.Lock(ctx)
	defer func() { task.Release(ctx) }()
	err := d.remove(ctx, &task)
	if err == nil {
		d.tasks.Delete(taskID)
	}
	return err
}

func (d *DockerRunner) remove(ctx context.Context, task *Task) (err error) {
	log.Debug(ctx, "removing", "task", task.ID)
	defer func() {
		if err != nil {
			log.Error(ctx, "cannot remove", "task", task.ID, "err", err)
		}
	}()
	if task.Status != TaskStatusTerminated {
		return fmt.Errorf("%w: cannot remove task %s with %s status", ErrRequest, task.ID, task.Status)
	}
	removeOptions := container.RemoveOptions{Force: true, RemoveVolumes: true}
	// Normally, it should not be empty
	if task.containerID != "" {
		err := d.client.ContainerRemove(ctx, task.containerID, removeOptions)
		if err != nil {
			if errdefs.IsNotFound(err) {
				log.Error(ctx, "cannot remove container: not found", "task", task.ID)
			} else {
				return fmt.Errorf("%w: failed to remove container task=%s: %w", ErrInternal, task.ID, err)
			}
		}
	}
	// Normally, it should not be empty
	if task.runnerDir != "" {
		// Failed attempts to remove or rename runner dir are considered non-fatal
		if err := os.RemoveAll(task.runnerDir); err != nil {
			log.Error(ctx, "failed to remove runner directory", "dir", task.runnerDir, "err", err)
			trashName := fmt.Sprintf(".trash-%s-%d", task.runnerDir, time.Now().UnixMicro())
			if err := os.Rename(task.runnerDir, trashName); err != nil {
				log.Error(ctx, "failed to rename runner directory", "dir", task.runnerDir, "err", err)
			}
		}
	}
	log.Debug(ctx, "removed", "task", task.ID)
	return nil
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

func prepareVolumes(ctx context.Context, taskConfig TaskConfig) error {
	for _, volume := range taskConfig.Volumes {
		err := formatAndMountVolume(ctx, volume)
		if err != nil {
			return tracerr.Wrap(err)
		}
	}
	return nil
}

func unmountVolumes(ctx context.Context, taskConfig TaskConfig) error {
	if len(taskConfig.Volumes) == 0 {
		return nil
	}
	log.Debug(ctx, "Unmounting volumes...")
	var failed []string
	for _, volume := range taskConfig.Volumes {
		mountPoint := getVolumeMountPoint(volume.Name)
		cmd := exec.Command("mountpoint", mountPoint)
		if output, err := cmd.CombinedOutput(); err != nil {
			log.Info(ctx, "skipping", "mountpoint", mountPoint, "output", output)
			continue
		}
		cmd = exec.Command("umount", "-qf", mountPoint)
		if output, err := cmd.CombinedOutput(); err != nil {
			log.Error(ctx, "failed to unmount", "mountpoint", mountPoint, "output", output)
			failed = append(failed, mountPoint)
		} else {
			log.Debug(ctx, "unmounted", "mountpoint", mountPoint)
		}
	}
	if len(failed) > 0 {
		return fmt.Errorf("failed to unmount volume(s): %v", failed)
	}
	return nil
}

func formatAndMountVolume(ctx context.Context, volume VolumeInfo) error {
	backend, err := getBackend(volume.Backend)
	if err != nil {
		return tracerr.Wrap(err)
	}
	deviceName, err := backend.GetRealDeviceName(volume.VolumeId, volume.DeviceName)
	if err != nil {
		return tracerr.Wrap(err)
	}
	fsCreated, err := initFileSystem(ctx, deviceName, !volume.InitFs)
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
	err = mountDisk(ctx, deviceName, getVolumeMountPoint(volume.Name), fsRootPerms)
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
func initFileSystem(ctx context.Context, deviceName string, errorIfNotExists bool) (bool, error) {
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

	log.Debug(ctx, "formatting disk with ext4 filesystem...", "device", deviceName)
	cmd = exec.Command("mkfs.ext4", "-F", deviceName)
	if output, err := cmd.CombinedOutput(); err != nil {
		return false, fmt.Errorf("failed to format disk: %w, output: %s", err, string(output))
	}
	log.Debug(ctx, "disk formatted succesfully!", "device", deviceName)
	return true, nil
}

func mountDisk(ctx context.Context, deviceName, mountPoint string, fsRootPerms os.FileMode) error {
	// Create the mount point directory if it doesn't exist
	if _, err := os.Stat(mountPoint); os.IsNotExist(err) {
		log.Debug(ctx, "creating mount point...", "mountpoint", mountPoint)
		if err := os.MkdirAll(mountPoint, 0o755); err != nil {
			return fmt.Errorf("failed to create mount point: %w", err)
		}
	}

	// Mount the disk to the mount point
	log.Debug(ctx, "mounting disk...", "device", deviceName, "mountpoint", mountPoint)
	cmd := exec.Command("mount", deviceName, mountPoint)
	if output, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("failed to mount disk: %w, output: %s", err, string(output))
	}

	if fsRootPerms != 0 {
		if err := os.Chmod(mountPoint, fsRootPerms); err != nil {
			return fmt.Errorf("failed to chmod volume root directory %s: %w", mountPoint, err)
		}
	}

	log.Debug(ctx, "disk mounted successfully!")
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
	regAuth, err := encodeRegistryAuth(taskConfig.RegistryUsername, taskConfig.RegistryPassword)
	if err != nil {
		log.Error(ctx, err.Error())
	}
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
			log.Error(ctx, "error pulling image", "name", taskConfig.ImageName, "err", progressRow.Error)
		}
		if strings.HasPrefix(progressRow.Status, "Status:") {
			status = true
			log.Debug(ctx, progressRow.Status)
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
		log.Debug(ctx, "image successfully pulled", "bytes", currentBytes, "bps", speed)
	} else {
		log.Error(ctx, "image pulling interrupted", "bytes", currentBytes, "total", totalBytes, "bps", speed)
	}

	err = ctx.Err()
	if err != nil {
		return tracerr.Errorf("imagepull interrupted: downloaded %d bytes out of %d (%s/s): %w", currentBytes, totalBytes, speed, err)
	}
	return nil
}

func (d *DockerRunner) createContainer(ctx context.Context, task *Task) (string, error) {
	runnerDir, err := d.dockerParams.MakeRunnerDir(task.containerName)
	if err != nil {
		return "", tracerr.Wrap(err)
	}
	task.runnerDir = runnerDir
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
		Cmd:          []string{strings.Join(d.dockerParams.DockerShellCommands(task.config.ContainerSshKeys), " && ")},
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
	hostConfig.Resources.NanoCPUs = int64(task.config.CPU * 1000000000)
	hostConfig.Resources.Memory = task.config.Memory
	if len(task.gpuIDs) > 0 {
		configureGpus(hostConfig, d.gpuVendor, task.gpuIDs)
	}
	configureHpcNetworkingIfAvailable(hostConfig)

	resp, err := d.client.ContainerCreate(ctx, containerConfig, hostConfig, nil, nil, task.containerName)
	if err != nil {
		return "", tracerr.Wrap(err)
	}
	return resp.ID, nil
}

func (d *DockerRunner) runContainer(ctx context.Context, task *Task) error {
	if err := d.client.ContainerStart(ctx, task.containerID, container.StartOptions{}); err != nil {
		return tracerr.Wrap(err)
	}

	waitCh, errorCh := d.client.ContainerWait(ctx, task.containerID, "")
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
		return "", fmt.Errorf("failed to encode auth config: %w", err)
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
		`if _exists apk; then _install() { apk add -U "$1"; }; fi`,
		// check in sshd is here, install if not
		`if ! _exists sshd; then _install openssh-server; fi`,
		// create ssh dirs and add public key
		"mkdir -p ~/.ssh",
		"chmod 700 ~/.ssh",
		fmt.Sprintf("echo '%s' > ~/.ssh/authorized_keys", publicSSHKey),
		"chmod 600 ~/.ssh/authorized_keys",
		`if [ -f ~/.profile ]; then sed -ie '1s@^@export PATH="'"$PATH"':$PATH"\n\n@' ~/.profile; fi`,
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
		fmt.Sprintf("/usr/sbin/sshd -p %d -o PidFile=none -o PasswordAuthentication=no -o AllowTcpForwarding=yes -o PermitUserEnvironment=yes", openSSHPort),
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
		// --device=/dev/dri/renderD<N>
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

func getContainerLastLogs(ctx context.Context, client docker.APIClient, containerID string, n int) ([]string, error) {
	options := container.LogsOptions{
		ShowStdout: true,
		ShowStderr: true,
		Tail:       fmt.Sprintf("%d", n),
	}

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
	commands = append(commands, fmt.Sprintf("%s %s", consts.RunnerBinaryPath, strings.Join(c.getRunnerArgs(), " ")))
	return commands
}

func (c *CLIArgs) DockerMounts(hostRunnerDir string) ([]mount.Mount, error) {
	return []mount.Mount{
		{
			Type:   mount.TypeBind,
			Source: hostRunnerDir,
			Target: consts.RunnerTempDir,
		},
		{
			Type:   mount.TypeBind,
			Source: c.Runner.BinaryPath,
			Target: consts.RunnerBinaryPath,
		},
	}, nil
}

func (c *CLIArgs) DockerPorts() []int {
	return []int{c.Runner.HTTPPort, c.Docker.SSHPort}
}

func (c *CLIArgs) MakeRunnerDir(name string) (string, error) {
	runnerTemp := filepath.Join(c.Shim.HomeDir, "runners", name)
	if err := os.MkdirAll(runnerTemp, 0o755); err != nil {
		return "", tracerr.Wrap(err)
	}
	return runnerTemp, nil
}
