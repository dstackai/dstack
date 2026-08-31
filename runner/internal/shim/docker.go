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
	"os/user"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	dockertypes "github.com/docker/docker/api/types"
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
	bytesize "github.com/inhies/go-bytesize"

	"github.com/dstackai/dstack/runner/internal/common/consts"
	"github.com/dstackai/dstack/runner/internal/common/gpu"
	"github.com/dstackai/dstack/runner/internal/common/log"
	"github.com/dstackai/dstack/runner/internal/common/types"
	"github.com/dstackai/dstack/runner/internal/shim/host"
)

// TODO: Allow for configuration via cli arguments or environment variables.
const ImagePullTimeout time.Duration = 20 * time.Minute

const (
	LabelKeyPrefix = "ai.dstack.shim."
	// Set to "true" on containers spawned by DockerRunner, used for identification.
	LabelKeyIsTask = LabelKeyPrefix + "is-task"
	LabelKeyTaskID = LabelKeyPrefix + "task-id"
	LabelValueTrue = "true"

	nvidiaModesetDevicePath = "/dev/nvidia-modeset"
)

type createContainerOptions struct {
	disableNvidiaDisplayCapability bool
}

// dockerd reports pulling progress as a stream of JSON Lines. The format of records is not documented in the API documentation,
// although it's occasionally mentioned, e.g., https://docs.docker.com/reference/api/engine/version-history/#v148-api-changes
// https://github.com/moby/moby/blob/e77ff99ede5ee5952b3a9227863552ae6e5b6fb1/pkg/jsonmessage/jsonmessage.go#L144
// All fields are optional.
type PullMessage struct {
	Id             string         `json:"id"` // layer id
	Status         string         `json:"status"`
	ProgressDetail ProgressDetail `json:"progressDetail"`
	ErrorDetail    struct {
		Message string `json:"message"`
	} `json:"errorDetail"`
}

type ProgressDetail struct {
	Current uint64 `json:"current"`
	Total   uint64 `json:"total"`
	Units   string `json:"units"`
}

func (p *ProgressDetail) isUnitBytes() bool {
	// > Units is the unit to print for progress. It defaults to "bytes" if empty
	// https://github.com/moby/moby/blob/8151a55a776f5f83f68bcf0030c19031439ea357/api/types/jsonstream/progress.go#L9
	return p.Units == "bytes" || p.Units == ""
}

type layerProgress struct {
	Status          string
	DownloadedBytes uint64
	ExtractedBytes  uint64
	TotalBytes      uint64
}

type PullTracker struct {
	mu     sync.RWMutex
	layers map[string]layerProgress
}

func newPullTracker() *PullTracker {
	return &PullTracker{layers: make(map[string]layerProgress)}
}

func (t *PullTracker) Update(msg PullMessage) {
	if msg.Id == "" {
		return
	}
	t.mu.Lock()
	defer t.mu.Unlock()
	layer := t.layers[msg.Id]
	switch msg.Status {
	case "Pulling fs layer", "Waiting", "Verifying Checksum", "Already exists":
		// no bytes to update, just track status
	case "Downloading":
		if msg.ProgressDetail.isUnitBytes() {
			layer.DownloadedBytes = msg.ProgressDetail.Current
			layer.TotalBytes = msg.ProgressDetail.Total
		}
	case "Download complete":
		layer.DownloadedBytes = layer.TotalBytes
	case "Extracting":
		if msg.ProgressDetail.isUnitBytes() {
			layer.ExtractedBytes = msg.ProgressDetail.Current
			layer.DownloadedBytes = msg.ProgressDetail.Total
			layer.TotalBytes = msg.ProgressDetail.Total
		}
	case "Pull complete":
		layer.ExtractedBytes = layer.TotalBytes
		layer.DownloadedBytes = layer.TotalBytes
	default:
		// Non-layer events, such as {"status":"Pulling from library/python","id":"3.11"}
		return
	}
	layer.Status = msg.Status
	t.layers[msg.Id] = layer
}

func (t *PullTracker) Progress() *ImagePullProgress {
	t.mu.RLock()
	defer t.mu.RUnlock()
	if len(t.layers) == 0 {
		return nil
	}
	p := ImagePullProgress{IsTotalBytesFinal: true}
	for _, l := range t.layers {
		if l.TotalBytes == 0 && l.Status != "Already exists" && l.Status != "Pull complete" {
			p.IsTotalBytesFinal = false
		}
		p.DownloadedBytes += l.DownloadedBytes
		p.ExtractedBytes += l.ExtractedBytes
		p.TotalBytes += l.TotalBytes
	}
	return &p
}

type DockerRunner struct {
	client       docker.APIClient
	dockerParams DockerParameters
	dockerInfo   dockersystem.Info
	baseEnv      []string
	gpus         []host.GpuInfo
	gpuVendor    gpu.GpuVendor
	gpuLock      *GpuLock
	tasks        TaskStorage
	// stateMu serializes task state file updates, see saveTaskState()
	stateMu sync.Mutex
	// authorizedKeysMu serializes authorized_keys updates, covering the whole
	// read-modify-write cycle, see reconcileHostSshKeys()
	authorizedKeysMu sync.Mutex
	// userLookup resolves a host user to its home dir and ids. Overridden in tests
	userLookup func(username string) (*user.User, error)
}

func NewDockerRunner(ctx context.Context, dockerParams DockerParameters) (*DockerRunner, error) {
	client, err := docker.NewClientWithOpts(docker.FromEnv, docker.WithAPIVersionNegotiation())
	if err != nil {
		return nil, fmt.Errorf("create docker client: %w", err)
	}
	dockerInfo, err := client.Info(ctx)
	if err != nil {
		return nil, fmt.Errorf("get docker info: %w", err)
	}

	// Copy variables once rather than on a per-task basis
	// We don't expect variables to change during the shim's lifetime
	baseEnv := []string{}
	for _, name := range dockerParams.DockerPassEnv() {
		if value, ok := os.LookupEnv(name); ok {
			baseEnv = append(baseEnv, fmt.Sprintf("%s=%s", name, value))
		}
	}

	var gpuVendor gpu.GpuVendor
	gpus := host.GetGpuInfo(ctx)
	if len(gpus) > 0 {
		gpuVendor = gpus[0].Vendor
	} else {
		gpuVendor = gpu.GpuVendorNone
	}
	gpuLock, err := NewGpuLock(gpus)
	if err != nil {
		return nil, fmt.Errorf("create GPU lock: %w", err)
	}

	runner := &DockerRunner{
		client:       client,
		dockerParams: dockerParams,
		dockerInfo:   dockerInfo,
		baseEnv:      baseEnv,
		gpus:         gpus,
		gpuVendor:    gpuVendor,
		gpuLock:      gpuLock,
		tasks:        NewTaskStorage(),
		userLookup:   user.Lookup,
	}

	// The task dirs are scanned once: the tasks whose dirs are claimed by a container
	// are restored, the dirs of the rest are orphaned and swept
	storedTasks := scanTaskDirs(ctx, dockerParams.TasksDir())
	if err := runner.restoreStateFromContainers(ctx, storedTasks); err != nil {
		return nil, fmt.Errorf("failed to restore state from containers: %w", err)
	}
	// Must be called after the tasks are restored, as it uses them to tell the dirs of
	// the live tasks from the orphaned ones
	runner.sweepOrphanedTaskDirs(ctx, storedTasks)
	// Brings authorized_keys in line with the restored tasks, dropping the entries left
	// by the tasks that are gone. Only the users of the restored tasks are reconciled;
	// the users of the swept tasks are already done by sweepOrphanedTaskDirs()
	if err := runner.reconcileHostSshKeys(ctx); err != nil {
		log.Error(ctx, "failed to reconcile host SSH keys on startup", "err", err)
	}

	return runner, nil
}

// taskContainerFilters returns filters matching all containers spawned by DockerRunner
func taskContainerFilters() filters.Args {
	return filters.NewArgs(filters.Arg("label", fmt.Sprintf("%s=%s", LabelKeyIsTask, LabelValueTrue)))
}

// restoreStateFromContainers regenerates TaskStorage and GpuLock inspecting containers
// and the task state files scanned by scanTaskDirs()
// Used to restore shim state on restarts
func (d *DockerRunner) restoreStateFromContainers(
	ctx context.Context, storedTasks map[string]storedTask,
) error {
	listOptions := container.ListOptions{All: true, Filters: taskContainerFilters()}
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
		var containerName string
		if len(containerShort.Names) > 0 {
			// "Names are prefixed with their parent and / == the docker daemon"
			// https://github.com/moby/moby/issues/6705
			containerName = strings.TrimLeft(containerShort.Names[0], "/")
		}
		var gpuIDs []string
		var ports []PortMapping
		if containerFull, err := d.client.ContainerInspect(ctx, containerID); err != nil {
			log.Error(ctx, "failed to inspect container", "id", containerID, "task", taskID)
		} else {
			switch d.gpuVendor {
			case gpu.GpuVendorNvidia:
				deviceRequests := containerFull.HostConfig.DeviceRequests
				if len(deviceRequests) == 1 {
					gpuIDs = deviceRequests[0].DeviceIDs
				} else if len(deviceRequests) != 0 {
					log.Error(
						ctx,
						"cannot extract GPU IDs from container: more than one DeviceRequest",
						"id", containerID, "task", taskID,
					)
				}
			case gpu.GpuVendorAmd:
				for _, device := range containerFull.HostConfig.Devices {
					if host.IsRenderNodePath(device.PathOnHost) {
						gpuIDs = append(gpuIDs, device.PathOnHost)
					}
				}
			case gpu.GpuVendorTenstorrent:
				for _, device := range containerFull.HostConfig.Devices {
					if strings.HasPrefix(device.PathOnHost, "/dev/tenstorrent/") {
						// Extract the device ID from the path
						deviceID := strings.TrimPrefix(device.PathOnHost, "/dev/tenstorrent/")
						gpuIDs = append(gpuIDs, deviceID)
					}
				}
			case gpu.GpuVendorIntel:
				for _, envVar := range containerFull.Config.Env {
					if indices, found := strings.CutPrefix(envVar, "HABANA_VISIBLE_DEVICES="); found {
						gpuIDs = strings.Split(indices, ",")
						break
					}
				}
			case gpu.GpuVendorNone:
				gpuIDs = []string{}
			}
			ports = extractPorts(ctx, containerFull.NetworkSettings.Ports)
		}
		storedTask, restored := storedTasks[taskID]
		state := storedTask.state
		config := state.Config
		taskDir := storedTask.dir
		if !restored {
			// Containers created by shim versions that did not write the state file have
			// no config to restore. The volumes can still be recovered from the container
			// mounts, unlike the host SSH keys, which are only known to the state file
			config.Volumes = volumesFromMounts(containerShort.Mounts)
			// Such a task still has a dir that must be removed along with the task
			taskDir = d.findLegacyTaskDir(containerName)
		}
		if state.CleanedUp {
			// The resources of this task, its GPUs included, have already been released,
			// therefore the task owns nothing
			gpuIDs = nil
		} else if len(gpuIDs) > 0 {
			// A GPU already locked by another restored task is not locked again and,
			// therefore, is not owned by this task -- otherwise, cleaning up this task
			// would release a GPU that the other one is still using
			gpuIDs = d.gpuLock.Lock(ctx, gpuIDs)
			log.Debug(ctx, "locked GPU(s) due to running task", "task", taskID, "gpus", gpuIDs)
		}
		// A task with a recorded termination reason has been terminated before the shim
		// restarted, and its reason must not be overridden by the container exit code.
		// Otherwise the task is restored as running regardless of the container state,
		// letting ProcessTasks() decide whether the container is still running and, if
		// it is not, why it finished
		status := TaskStatusRunning
		if state.TerminationReason != "" {
			status = TaskStatusTerminated
		}
		task := NewTask(taskID, status)
		task.TerminationReason = state.TerminationReason
		task.TerminationMessage = state.TerminationMessage
		task.config = config
		task.containerName = containerName
		task.containerID = containerID
		task.gpuIDs = gpuIDs
		task.ports = ports
		task.taskDir = taskDir
		task.cleanedUp = state.CleanedUp
		if !d.tasks.Add(task) {
			log.Error(ctx, "duplicate restored task", "task", taskID)
			// Nothing will release the GPUs of a task that is not stored
			d.gpuLock.Release(ctx, gpuIDs)
			continue
		}
		log.Debug(
			ctx, "restored task",
			"task", taskID, "status", status, "state", containerShort.State, "gpus", gpuIDs,
		)
	}
	return nil
}

// volumesFromMounts recovers the volumes attached to a task from its container mounts.
// Only the volume names are recovered, which is all that is needed to unmount them
func volumesFromMounts(mounts []dockertypes.MountPoint) []VolumeInfo {
	var volumes []VolumeInfo
	for _, mount := range mounts {
		if name, found := strings.CutPrefix(mount.Source, volumeMountPointDir+"/"); found {
			volumes = append(volumes, VolumeInfo{Name: name})
		}
	}
	return volumes
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

// Gpus returns the GPUs detected at startup without collecting other host
// resources, making it suitable for frequently called paths.
func (d *DockerRunner) Gpus(ctx context.Context) []host.GpuInfo {
	return d.gpus
}

func (d *DockerRunner) TaskList() []*TaskListItem {
	tasks := d.tasks.List()
	result := make([]*TaskListItem, 0, len(tasks))
	for _, task := range tasks {
		result = append(result, &TaskListItem{ID: task.ID, Status: task.Status})
	}
	return result
}

func (d *DockerRunner) TaskInfo(taskID string) TaskInfo {
	task, ok := d.tasks.Get(taskID)
	if !ok {
		return TaskInfo{}
	}
	return TaskInfo{
		ID:                 task.ID,
		Status:             task.Status,
		TerminationReason:  task.TerminationReason,
		TerminationMessage: task.TerminationMessage,
		Ports:              task.ports,
		ContainerName:      task.containerName,
		ContainerID:        task.containerID,
		GpuIDs:             task.gpuIDs,
		ImagePullProgress:  task.pullTracker.Progress(),
	}
}

func (d *DockerRunner) Submit(ctx context.Context, cfg TaskConfig) error {
	task := NewTaskFromConfig(cfg)
	if ok := d.tasks.Add(task); !ok {
		return fmt.Errorf("%w: task %s is already submitted", ErrRequest, task.ID)
	}
	log.Debug(ctx, "new task submitted", "task", task.ID)
	return nil
}

// commit applies mutate to the stored task and, on success, updates the local copy
// of the task accordingly. mutate is called before the local copy is updated, so it
// can read the local copy to publish fields set by the caller, e.g., containerID.
// The local copy is left intact if the update is rejected.
func (d *DockerRunner) commit(ctx context.Context, task *Task, mutate func(*Task)) error {
	updatedTask, err := d.tasks.Modify(task.ID, func(t *Task) error {
		mutate(t)
		return nil
	})
	if err != nil {
		return err
	}
	*task = updatedTask
	d.saveTaskState(ctx, task.ID)
	return nil
}

// commitTerminated commits the terminated status set on the local copy of the task.
// Used by operations that set the status on their failure paths, where committing it
// at every such path would be too verbose.
func (d *DockerRunner) commitTerminated(ctx context.Context, task *Task) {
	if task.Status != TaskStatusTerminated {
		// the last successful commit is the actual state, nothing to commit
		return
	}
	if err := d.commit(ctx, task, func(t *Task) {
		t.SetStatusTerminated(task.TerminationReason, task.TerminationMessage)
	}); err != nil && !errors.Is(err, ErrNotFound) {
		log.Error(ctx, "failed to commit terminated status", "task", task.ID, "err", err)
	}
}

// Start prepares the task resources, pulls the image, and starts the container.
// It returns as soon as the container is started, that is, it does not wait for the
// container to exit. Detecting the exit, terminating the task, and releasing its
// resources is the responsibility of ProcessTasks().
// If the task cannot be started, it is terminated and its resources are released
// before returning, except for the resources that cannot be released while the
// container may be running -- those are left to ProcessTasks() as well.
func (d *DockerRunner) Start(ctx context.Context, taskID string) (err error) {
	task, ok := d.tasks.Get(taskID)
	if !ok {
		log.Error(ctx, "cannot start: not found", "task", taskID)
		return fmt.Errorf("task %s: %w", taskID, ErrNotFound)
	}

	if task.Status != TaskStatusPending {
		return fmt.Errorf("%w: cannot start task %s with %s status", ErrRequest, task.ID, task.Status)
	}

	// The task is owned by this method until it returns: ProcessTasks() skips tasks
	// in flight, so that it does not release the resources acquired here
	started := false
	defer func() {
		if !started {
			if err != nil && task.Status != TaskStatusTerminated {
				// a failure path that has not terminated the task, e.g., a rejected update
				task.SetStatusTerminated(string(types.TerminationReasonExecutorError), err.Error())
			}
			if task.containerID == "" {
				// There is no container that may be running, so it is safe to release
				// the resources now. Otherwise, ProcessTasks() releases them once the
				// container is not running
				task.Lock(ctx)
				d.cleanupLocked(ctx, &task)
				task.Release(ctx)
			}
		}
		// Hand the task over to ProcessTasks()
		if commitErr := d.commit(ctx, &task, func(t *Task) {
			t.startInFlight = false
			if task.containerID != "" {
				t.containerID = task.containerID
			}
			if task.cleanedUp {
				t.cleanedUp = true
			}
			if task.Status == TaskStatusTerminated {
				t.SetStatusTerminated(task.TerminationReason, task.TerminationMessage)
			}
		}); commitErr != nil && !errors.Is(commitErr, ErrNotFound) {
			log.Error(ctx, "failed to commit final state", "task", task.ID, "err", commitErr)
		}
	}()

	if err := d.commit(ctx, &task, func(t *Task) {
		t.startInFlight = true
		t.SetStatusPreparing()
	}); err != nil {
		return fmt.Errorf("%w: failed to update task %s: %w", ErrInternal, task.ID, err)
	}

	cfg := task.config

	taskDir, err := d.dockerParams.MakeTaskDir(task.containerName)
	if err != nil {
		return fmt.Errorf("make task dir: %w", err)
	}
	log.Trace(ctx, "task dir", "task", task.ID, "path", taskDir)
	// Resources are committed as soon as they are acquired, so that they are not
	// lost if the task is updated by another goroutine, e.g., terminated by the server
	if err := d.commit(ctx, &task, func(t *Task) { t.taskDir = taskDir }); err != nil {
		return fmt.Errorf("%w: failed to update task %s: %w", ErrInternal, task.ID, err)
	}

	var gpuIDs []string
	if cfg.GPU != 0 {
		gpuIDs, err = d.gpuLock.Acquire(ctx, cfg.GPU)
		if err != nil {
			log.Error(ctx, err.Error())
			task.SetStatusTerminated(string(types.TerminationReasonExecutorError), err.Error())
			return fmt.Errorf("acquire GPU: %w", err)
		}
		log.Debug(ctx, "acquired GPU(s)", "task", task.ID, "gpus", gpuIDs)
	} else {
		gpuIDs = []string{}
	}
	if err := d.commit(ctx, &task, func(t *Task) { t.gpuIDs = gpuIDs }); err != nil {
		return fmt.Errorf("%w: failed to update task %s: %w", ErrInternal, task.ID, err)
	}

	if len(cfg.HostSshKeys) > 0 {
		// No user is passed: the task is already stored and not cleaned up by now,
		// therefore its own keys are a part of the reconciled set
		if err := d.reconcileHostSshKeys(ctx); err != nil {
			errMessage := fmt.Sprintf("reconcileHostSshKeys error: %s", err.Error())
			log.Error(ctx, errMessage)
			task.SetStatusTerminated(string(types.TerminationReasonExecutorError), errMessage)
			return fmt.Errorf("reconcile host SSH keys: %w", err)
		}
	}

	// Volumes mounted by a failed prepareVolumes() call are unmounted by cleanupLocked()
	err = prepareVolumes(ctx, cfg)
	if err != nil {
		errMessage := fmt.Sprintf("prepareVolumes error: %s", err.Error())
		log.Error(ctx, errMessage)
		task.SetStatusTerminated(string(types.TerminationReasonExecutorError), errMessage)
		return fmt.Errorf("prepare volumes: %w", err)
	}
	err = prepareInstanceMountPoints(cfg)
	if err != nil {
		errMessage := fmt.Sprintf("prepareInstanceMountPoints error: %s", err.Error())
		log.Error(ctx, errMessage)
		task.SetStatusTerminated(string(types.TerminationReasonExecutorError), errMessage)
		return fmt.Errorf("prepare instance mount points: %w", err)
	}

	log.Debug(ctx, "Pulling image")
	pullCtx, cancelPull := context.WithTimeout(ctx, ImagePullTimeout)
	defer cancelPull()
	if err := d.commit(ctx, &task, func(t *Task) { t.SetStatusPulling(cancelPull) }); err != nil {
		return fmt.Errorf("%w: failed to update task %s: %w", ErrInternal, task.ID, err)
	}
	pullLogPath := filepath.Join(taskDir, "pull.log")
	if err = pullImage(pullCtx, d.client, cfg, pullLogPath, task.pullTracker); err != nil {
		errMessage := fmt.Sprintf("pullImage error: %s", err.Error())
		log.Error(ctx, errMessage)
		task.SetStatusTerminated(string(types.TerminationReasonCreatingContainerError), errMessage)
		return fmt.Errorf("pull image: %w", err)
	}

	log.Debug(ctx, "Creating container", "task", task.ID, "name", task.containerName)
	if err := d.commit(ctx, &task, func(t *Task) { t.SetStatusCreating() }); err != nil {
		return fmt.Errorf("%w: failed to update task %s: %w", ErrInternal, task.ID, err)
	}
	if err := d.createContainer(ctx, &task, createContainerOptions{}); err != nil {
		errMessage := fmt.Sprintf("createContainer error: %s", err.Error())
		log.Error(ctx, errMessage)
		task.SetStatusTerminated(string(types.TerminationReasonCreatingContainerError), errMessage)
		return fmt.Errorf("create container: %w", err)
	}

	log.Debug(ctx, "Starting container", "task", task.ID, "name", task.containerName)
	err = d.startContainer(ctx, &task)
	if len(task.config.GPUDevices) == 0 &&
		shouldRetryWithoutNvidiaDisplayCapability(d.gpuVendor, err) {
		log.Warning(ctx, "retrying container without NVIDIA display capability", "task", task.ID, "err", err)
		if removeErr := d.removeContainer(ctx, &task); removeErr != nil {
			err = fmt.Errorf("remove container before retry: %w", removeErr)
		} else if createErr := d.createContainer(
			ctx,
			&task,
			createContainerOptions{disableNvidiaDisplayCapability: true},
		); createErr != nil {
			err = fmt.Errorf("create container without NVIDIA display capability: %w", createErr)
		} else {
			err = d.startContainer(ctx, &task)
		}
	}
	if err != nil {
		log.Error(ctx, "failed to start container", "task", task.ID, "err", err)
		var errMessage string
		if lastLogs, logsErr := getContainerLastLogs(ctx, d.client, task.containerID, 5); logsErr == nil {
			errMessage = strings.Join(lastLogs, "\n")
		} else {
			log.Error(ctx, "getContainerLastLogs error", "err", logsErr)
		}
		task.SetStatusTerminated(string(types.TerminationReasonContainerExitedWithError), errMessage)
		return fmt.Errorf("start container: %w", err)
	}

	// The container is running, the task is now processed in the background
	if err := d.commit(ctx, &task, func(t *Task) {
		// startContainer sets the ports field, the retry above may have
		// replaced the container
		t.containerID = task.containerID
		t.ports = task.ports
		t.startInFlight = false
		t.SetStatusRunning()
	}); err != nil {
		return fmt.Errorf("%w: failed to update task %s: %w", ErrInternal, task.ID, err)
	}
	started = true

	log.Debug(ctx, "Task started", "task", task.ID, "name", task.containerName)

	return nil
}

// cleanupLocked releases the resources acquired for the task: host SSH keys,
// volumes, and GPUs. The container must not be running, otherwise unmounting
// volumes may fail.
// It is safe to call it more than once: the resources are released only if they
// have not been released yet.
// The task lock must be held by the caller.
func (d *DockerRunner) cleanupLocked(ctx context.Context, task *Task) {
	if task.cleanedUp {
		return
	}
	// Another operation may have released the resources while we were waiting for
	// the task lock, therefore the stored task is the source of truth
	if storedTask, ok := d.tasks.Get(task.ID); ok && storedTask.cleanedUp {
		task.cleanedUp = true
		return
	}
	log.Debug(ctx, "releasing task resources", "task", task.ID)
	task.cleanedUp = true
	// The flag is committed _before_ the resources are released, so that the host SSH
	// keys of this task are already out of the reconciled set by the time
	// releaseTaskResources() computes it. This is safe if the shim stops running in
	// between: the state file is only written at the end, therefore the task is cleaned
	// up again, idempotently, after a restart.
	// Commit the flag without touching the rest of the local copy of the task,
	// which may contain uncommitted changes made by the caller
	if _, err := d.tasks.Modify(task.ID, func(t *Task) error {
		t.cleanedUp = true
		return nil
	}); err != nil && !errors.Is(err, ErrNotFound) {
		log.Error(ctx, "failed to commit cleaned up state", "task", task.ID, "err", err)
	}
	d.releaseTaskResources(ctx, task.config)
	if len(task.gpuIDs) > 0 {
		releasedGpuIDs := d.gpuLock.Release(ctx, task.gpuIDs)
		log.Debug(ctx, "released GPU(s)", "task", task.ID, "gpus", releasedGpuIDs)
	}
	d.saveTaskState(ctx, task.ID)
}

// releaseTaskResources releases the host resources acquired for a task: volumes and
// host SSH keys. Unlike GPU locks, which are only kept in memory, these outlive the
// shim process, therefore they are released by task config and not by task.
// The task must already be marked as cleaned up, or gone from TaskStorage altogether,
// otherwise its host SSH keys are still considered to be in use
func (d *DockerRunner) releaseTaskResources(ctx context.Context, cfg TaskConfig) {
	if err := unmountVolumes(ctx, cfg); err != nil {
		log.Error(ctx, "failed to unmount volumes", "err", err)
	}
	if len(cfg.HostSshKeys) > 0 {
		if err := d.reconcileHostSshKeys(ctx, cfg.HostSshUser); err != nil {
			log.Error(ctx, "failed to reconcile host SSH keys", "err", err)
		}
	}
}

// reconcileHostSshKeys brings the shim-owned entries of the host users' authorized_keys
// files in line with the tasks that still need them, that is, with the keys of all the
// stored tasks that have not been cleaned up yet.
//
// extraUsers are reconciled on top of the users of those tasks. Only a user whose tasks
// contribute no keys needs it: once the last task of a user is cleaned up, or gone from
// TaskStorage altogether, nothing names that user anymore, yet its entries are still in
// the file and have to be dropped.
//
// A failure for one user does not keep the other users from being reconciled; all the
// failures are returned joined, for the caller to report.
func (d *DockerRunner) reconcileHostSshKeys(ctx context.Context, extraUsers ...string) error {
	// The lock is held for the whole read-modify-write cycle, so that a stale set of
	// keys cannot overwrite a newer one. Nothing takes a task lock while holding it,
	// therefore it cannot deadlock with the task lock its callers may hold
	d.authorizedKeysMu.Lock()
	defer d.authorizedKeysMu.Unlock()

	// Seeding the map is what makes the loop at the end visit the extra users: a user
	// that no task names has no entry in the map, and so is never reconciled
	keysByUser := make(map[string][]string, len(extraUsers))
	for _, username := range extraUsers {
		keysByUser[username] = nil
	}
	for _, task := range d.tasks.List() {
		cfg := task.config
		if task.cleanedUp || len(cfg.HostSshKeys) == 0 {
			continue
		}
		keysByUser[cfg.HostSshUser] = append(keysByUser[cfg.HostSshUser], cfg.HostSshKeys...)
	}

	var errs []error
	for username, keys := range keysByUser {
		ak := AuthorizedKeys{user: username, lookup: d.userLookup}
		if err := ak.Reconcile(ctx, keys); err != nil {
			errs = append(errs, fmt.Errorf("user %s: %w", username, err))
		}
	}
	return errors.Join(errs...)
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
	// The task may have been updated while we were acquiring the lock
	if task, ok = d.tasks.Get(taskID); !ok {
		log.Error(ctx, "cannot terminate task: not found", "task", taskID)
		return fmt.Errorf("task %s: %w", taskID, ErrNotFound)
	}
	defer func() { d.commitTerminated(ctx, &task) }()
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
		if err := d.stopContainer(ctx, task.containerID, int(timeout)); err != nil {
			return err
		}
	default:
		return fmt.Errorf("%w: should not reach here", ErrInternal)
	}
	if !task.startInFlight {
		// The container, if any, is not running anymore, so it is safe to release
		// the resources. If the task is in flight, Start() owns the resources
		// and releases them itself
		d.cleanupLocked(ctx, task)
	}
	task.SetStatusTerminated(reason, message)
	// Logged a level below the spontaneous termination reported by ProcessTasks():
	// this one is requested by the caller, which reports it on its own
	log.Debug(ctx, "terminated", "task", task.ID, "reason", reason)
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
	// The task may have been updated while we were acquiring the lock
	if task, ok = d.tasks.Get(taskID); !ok {
		log.Error(ctx, "cannot remove: not found", "task", taskID)
		return fmt.Errorf("task %s: %w", taskID, ErrNotFound)
	}
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
	// Normally, it should not be empty
	if err := d.removeContainer(ctx, task); err != nil {
		return err
	}
	// Normally, the resources are already released by ProcessTasks() or Terminate(),
	// but the task may be removed before that happens
	d.cleanupLocked(ctx, task)
	// Normally, it should not be empty
	if task.taskDir != "" {
		// Failed attempts to remove or rename task dir are considered non-fatal
		if err := os.RemoveAll(task.taskDir); err != nil {
			log.Error(ctx, "failed to remove task directory", "dir", task.taskDir, "err", err)
			trashName := filepath.Join(
				filepath.Dir(task.taskDir),
				fmt.Sprintf(".trash-%s-%d", filepath.Base(task.taskDir), time.Now().UnixMicro()),
			)
			if err := os.Rename(task.taskDir, trashName); err != nil {
				log.Error(ctx, "failed to rename task directory", "dir", task.taskDir, "err", err)
			}
		}
	}
	log.Debug(ctx, "removed", "task", task.ID)
	return nil
}

func (d *DockerRunner) removeContainer(ctx context.Context, task *Task) error {
	if task.containerID == "" {
		return nil
	}
	removeOptions := container.RemoveOptions{Force: true, RemoveVolumes: true}
	err := d.client.ContainerRemove(ctx, task.containerID, removeOptions)
	if err != nil {
		if errdefs.IsNotFound(err) {
			log.Error(ctx, "cannot remove container: not found", "task", task.ID)
			task.containerID = ""
			return nil
		}
		return fmt.Errorf("%w: failed to remove container task=%s: %w", ErrInternal, task.ID, err)
	}
	task.containerID = ""
	return nil
}

func pullImage(ctx context.Context, client docker.APIClient, taskConfig TaskConfig, logPath string, tracker *PullTracker) error {
	if !strings.Contains(taskConfig.ImageName, ":") {
		taskConfig.ImageName += ":latest"
	}
	images, err := client.ImageList(ctx, image.ListOptions{
		Filters: filters.NewArgs(filters.Arg("reference", taskConfig.ImageName)),
	})
	if err != nil {
		return fmt.Errorf("list images: %w", err)
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
		return fmt.Errorf("pull image: %w", err)
	}
	defer func() { _ = reader.Close() }()

	logFile, err := os.OpenFile(logPath, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o644)
	if err != nil {
		return fmt.Errorf("open pull log file: %w", err)
	}
	defer logFile.Close()

	teeReader := io.TeeReader(reader, logFile)

	var pullCompleted bool
	pullErrors := make([]string, 0)

	scanner := bufio.NewScanner(teeReader)
	for scanner.Scan() {
		line := scanner.Bytes()
		var pullMessage PullMessage
		if err := json.Unmarshal(line, &pullMessage); err != nil {
			continue
		}
		tracker.Update(pullMessage)
		if pullMessage.ErrorDetail.Message != "" {
			log.Error(ctx, "error pulling image", "name", taskConfig.ImageName, "err", pullMessage.ErrorDetail.Message)
			pullErrors = append(pullErrors, pullMessage.ErrorDetail.Message)
		}
		// If the pull is successful, the last two entries must be:
		// "Digest: sha256:<hash>"
		// "Status: <message>"
		// where <message> is either "Downloaded newer image for <tag>" or "Image is up to date for <tag>".
		// See: https://github.com/moby/moby/blob/e77ff99ede5ee5952b3a9227863552ae6e5b6fb1/daemon/containerd/image_pull.go#L134-L152
		// See: https://github.com/moby/moby/blob/e77ff99ede5ee5952b3a9227863552ae6e5b6fb1/daemon/containerd/image_pull.go#L257-L263
		if strings.HasPrefix(pullMessage.Status, "Status:") {
			pullCompleted = true
			log.Debug(ctx, pullMessage.Status)
		}
	}

	duration := time.Since(startTime)
	p := tracker.Progress()
	var currentBytes, totalBytes uint64
	if p != nil {
		currentBytes, totalBytes = p.DownloadedBytes, p.TotalBytes
	}
	speed := bytesize.New(float64(currentBytes) / duration.Seconds())

	if err := ctx.Err(); err != nil {
		return fmt.Errorf("image pull interrupted: downloaded %d bytes out of %d (%s/s): %w", currentBytes, totalBytes, speed, err)
	}

	if pullCompleted {
		log.Debug(ctx, "image successfully pulled", "bytes", currentBytes, "bps", speed)
	} else {
		return fmt.Errorf(
			"failed pulling %s: downloaded %d/%d bytes (%s/s), errors: %q",
			taskConfig.ImageName, currentBytes, totalBytes, speed, pullErrors,
		)
	}

	return nil
}

func (d *DockerRunner) createContainer(
	ctx context.Context,
	task *Task,
	options createContainerOptions,
) error {
	mounts, err := d.dockerParams.DockerMounts(task.taskDir)
	if err != nil {
		return fmt.Errorf("get docker mounts: %w", err)
	}
	volumeMounts, err := getVolumeMounts(task.config.VolumeMounts)
	if err != nil {
		return fmt.Errorf("get volume mounts: %w", err)
	}
	mounts = append(mounts, volumeMounts...)
	instanceMounts, err := getInstanceMounts(task.config.InstanceMounts)
	if err != nil {
		return fmt.Errorf("get instance mounts: %w", err)
	}
	mounts = append(mounts, instanceMounts...)

	// Set the environment variables
	envVars := []string{}
	envVars = append(envVars, d.baseEnv...)
	if pjrtDevice := d.dockerParams.DockerPJRTDevice(); pjrtDevice != "" {
		envVars = append(envVars, fmt.Sprintf("PJRT_DEVICE=%s", pjrtDevice))
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

	networkMode := getNetworkMode(task.config.NetworkMode)
	ports := d.dockerParams.DockerPorts()

	// Bridge mode - all interfaces
	runnerHttpAddress := ""
	if networkMode.IsHost() {
		runnerHttpAddress = "localhost"
	}
	shellCommands := d.dockerParams.DockerShellCommands(task.config.ContainerSshKeys, runnerHttpAddress)

	containerConfig := &container.Config{
		Image:        task.config.ImageName,
		Cmd:          []string{strings.Join(shellCommands, " && ")},
		Entrypoint:   []string{"/bin/sh", "-c"},
		ExposedPorts: exposePorts(ports),
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
		Privileged:   task.config.Privileged || d.dockerParams.DockerPrivileged(),
		NetworkMode:  networkMode,
		PortBindings: bindPorts(ports),
		Mounts:       mounts,
		ShmSize:      task.config.ShmSize,
		Tmpfs:        tmpfs,
	}
	hostConfig.NanoCPUs = int64(task.config.CPU * 1000000000)
	hostConfig.Memory = task.config.Memory
	if len(task.gpuIDs) > 0 {
		if len(task.config.GPUDevices) > 0 {
			configureGpuDevices(hostConfig, task.config.GPUDevices)
		} else {
			configureGpus(containerConfig, hostConfig, d.gpuVendor, task.gpuIDs, options)
		}
	}
	configureHpcNetworkingIfAvailable(hostConfig)

	resp, err := d.client.ContainerCreate(ctx, containerConfig, hostConfig, nil, nil, task.containerName)
	if err != nil {
		return fmt.Errorf("create container: %w", err)
	}
	task.containerID = resp.ID
	return nil
}

func shouldRetryWithoutNvidiaDisplayCapability(vendor gpu.GpuVendor, err error) bool {
	return vendor == gpu.GpuVendorNvidia &&
		err != nil &&
		strings.Contains(err.Error(), nvidiaModesetDevicePath)
}

func (d *DockerRunner) startContainer(ctx context.Context, task *Task) error {
	if err := d.client.ContainerStart(ctx, task.containerID, container.StartOptions{}); err != nil {
		return fmt.Errorf("start container: %w", err)
	}
	if getNetworkMode(task.config.NetworkMode).IsHost() {
		task.ports = []PortMapping{}
		return nil
	}
	container_, err := d.client.ContainerInspect(ctx, task.containerID)
	if err != nil {
		return fmt.Errorf("inspect container: %w", err)
	}
	task.ports = extractPorts(ctx, container_.NetworkSettings.Ports)
	return nil
}

// stopContainer stops the container, waiting for it to exit. The container is
// killed if it does not exit gracefully within timeout seconds.
func (d *DockerRunner) stopContainer(ctx context.Context, containerID string, timeout int) error {
	stopOptions := container.StopOptions{Timeout: &timeout}
	if err := d.client.ContainerStop(ctx, containerID, stopOptions); err != nil {
		return fmt.Errorf("%w: failed to stop container: %w", ErrInternal, err)
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

func getSSHShellCommands() []string {
	return []string{
		`( :`,
		// See https://github.com/dstackai/dstack/issues/1769
		`unset LD_LIBRARY_PATH && unset LD_PRELOAD`,
		// common functions
		`exists() { command -v "$1" > /dev/null 2>&1; }`,
		// package manager detection/abstraction
		`install_pkg() { NAME=Distribution; test -f /etc/os-release && . /etc/os-release; echo $NAME not supported; exit 11; }`,
		`if exists apt-get; then install_pkg() { apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y "$1"; }; fi`,
		`if exists yum; then install_pkg() { yum install -y "$1"; }; fi`,
		`if exists apk; then install_pkg() { apk add -U "$1"; }; fi`,
		// check in sshd is here, install if not
		`if ! exists sshd; then install_pkg openssh-server; fi`,
		`: )`,
	}
}

func exposePorts(ports []int) nat.PortSet {
	portSet := make(nat.PortSet)
	for _, port := range ports {
		portSet[nat.Port(fmt.Sprintf("%d/tcp", port))] = struct{}{}
	}
	return portSet
}

// bindPorts does identity mapping only
func bindPorts(ports []int) nat.PortMap {
	portMap := make(nat.PortMap)
	for _, port := range ports {
		portMap[nat.Port(fmt.Sprintf("%d/tcp", port))] = []nat.PortBinding{
			{
				HostIP:   "127.0.0.1",
				HostPort: "", // use ephemeral port from ip_local_port_range
			},
		}
	}
	return portMap
}

func extractPorts(ctx context.Context, portMap nat.PortMap) []PortMapping {
	ports := make([]PortMapping, 0, len(portMap))
	for containerPortWithProto, bindings := range portMap {
		// 8080/tcp -> ["8080", "tcp"]
		containerPortParts := strings.Split(string(containerPortWithProto), "/")
		if len(containerPortParts) != 2 {
			log.Error(ctx, "unexpected container port format", "port", containerPortWithProto)
			continue
		}
		if containerPortParts[1] != "tcp" {
			continue
		}
		containerPort, err := strconv.Atoi(containerPortParts[0])
		if err != nil {
			log.Error(ctx, "failed to parse container port", "port", containerPortWithProto)
			continue
		}
		for _, binding := range bindings {
			// skip IPv6
			if strings.Contains(binding.HostIP, ":") {
				continue
			}
			hostPort, err := strconv.Atoi(binding.HostPort)
			if err != nil {
				log.Error(ctx, "failed to parse host port", "port", binding.HostPort)
				continue
			}
			ports = append(ports, PortMapping{
				Host:      hostPort,
				Container: containerPort,
			})
		}
	}
	return ports
}

func getNetworkMode(networkMode NetworkMode) container.NetworkMode {
	return container.NetworkMode(networkMode)
}

func configureGpuDevices(hostConfig *container.HostConfig, gpuDevices []GPUDevice) {
	for _, gpuDevice := range gpuDevices {
		hostConfig.Devices = append(
			hostConfig.Devices,
			container.DeviceMapping{
				PathOnHost:        gpuDevice.PathOnHost,
				PathInContainer:   gpuDevice.PathInContainer,
				CgroupPermissions: "rwm",
			},
		)
	}
}

func configureGpus(
	config *container.Config,
	hostConfig *container.HostConfig,
	vendor gpu.GpuVendor,
	ids []string,
	options createContainerOptions,
) {
	// NVIDIA: ids are identifiers reported by nvidia-smi, GPU-<UUID> strings
	// AMD: ids are DRI render node paths, e.g., /dev/dri/renderD128
	// Tenstorrent: ids are device indices to be used with /dev/tenstorrent/<id>
	switch vendor {
	case gpu.GpuVendorNvidia:
		hostConfig.DeviceRequests = append(
			hostConfig.DeviceRequests,
			container.DeviceRequest{
				// Request the existing broad capability set by default. If the host fails due to
				// a missing modeset device, retry without the X11 display capability.
				// Docker's default capabilities: utility, compute.
				// https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/docker-specialized.html
				Capabilities: [][]string{nvidiaDeviceRequestCapabilities(options)},
				DeviceIDs:    ids,
			},
		)
	case gpu.GpuVendorAmd:
		// All options are listed here: https://hub.docker.com/r/rocm/pytorch
		// Only --device are mandatory, other seem to be performance-related.
		// --device=/dev/kfd
		hostConfig.Devices = append(
			hostConfig.Devices,
			container.DeviceMapping{
				PathOnHost:        "/dev/kfd",
				PathInContainer:   "/dev/kfd",
				CgroupPermissions: "rwm",
			},
		)
		// --device=/dev/dri/renderD<N>
		for _, renderNodePath := range ids {
			hostConfig.Devices = append(
				hostConfig.Devices,
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
	case gpu.GpuVendorTenstorrent:
		// For Tenstorrent, simply add each device
		for _, id := range ids {
			devicePath := fmt.Sprintf("/dev/tenstorrent/%s", id)
			hostConfig.Devices = append(
				hostConfig.Devices,
				container.DeviceMapping{
					PathOnHost:        devicePath,
					PathInContainer:   devicePath,
					CgroupPermissions: "rwm",
				},
			)
		}
		// Check and mount hugepages-1G if it exists
		if _, err := os.Stat("/dev/hugepages-1G"); err == nil {
			hostConfig.Mounts = append(hostConfig.Mounts, mount.Mount{
				Type:   mount.TypeBind,
				Source: "/dev/hugepages-1G",
				Target: "/dev/hugepages-1G",
			})
		}
	case gpu.GpuVendorIntel:
		// All options are listed here:
		// https://docs.habana.ai/en/latest/Installation_Guide/Additional_Installation/Docker_Installation.html
		// --runtime=habana
		hostConfig.Runtime = "habana"
		// --ipc=host
		hostConfig.IpcMode = container.IPCModeHost
		// --cap-add=SYS_NICE
		hostConfig.CapAdd = append(hostConfig.CapAdd, "SYS_NICE")
		// -e HABANA_VISIBLE_DEVICES=0,1,...
		config.Env = append(config.Env, fmt.Sprintf("HABANA_VISIBLE_DEVICES=%s", strings.Join(ids, ",")))
	case gpu.GpuVendorNone:
		// nothing to do
	}
}

func nvidiaDeviceRequestCapabilities(options createContainerOptions) []string {
	capabilities := []string{"gpu", "utility", "compute", "graphics", "video"}
	if !options.disableNvidiaDisplayCapability {
		capabilities = append(capabilities, "display")
	}
	capabilities = append(capabilities, "compat32")
	return capabilities
}

func configureHpcNetworkingIfAvailable(hostConfig *container.HostConfig) {
	// Although AWS EFA is not InfiniBand, EFA adapters are exposed as /dev/infiniband/uverbsN (N=0,1,...)
	if _, err := os.Stat("/dev/infiniband"); !errors.Is(err, os.ErrNotExist) {
		hostConfig.Devices = append(
			hostConfig.Devices,
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
	defer func() { _ = muxedReader.Close() }()

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

func (c *CLIArgs) DockerPassEnv() []string {
	names := []string{}
	for _, name := range strings.Split(c.Docker.PassEnv, ",") {
		if name = strings.TrimSpace(name); name != "" {
			names = append(names, name)
		}
	}
	return names
}

func (c *CLIArgs) DockerPrivileged() bool {
	return c.Docker.Privileged
}

func (c *CLIArgs) DockerPJRTDevice() string {
	return c.Docker.PJRTDevice
}

func (c *CLIArgs) DockerShellCommands(authorizedKeys []string, runnerHttpAddress string) []string {
	commands := getSSHShellCommands()
	runnerCommand := []string{
		consts.RunnerBinaryPath,
		"--log-level", c.Runner.LogLevel,
		"start",
		"--temp-dir", consts.RunnerTempDir,
		"--http-port", strconv.Itoa(c.Runner.HTTPPort),
		"--ssh-port", strconv.Itoa(c.Runner.SSHPort),
	}
	if runnerHttpAddress != "" {
		runnerCommand = append(runnerCommand, "--http-address", runnerHttpAddress)
	}
	for _, key := range authorizedKeys {
		runnerCommand = append(runnerCommand, "--ssh-authorized-key", fmt.Sprintf("'%s'", key))
	}
	if c.Runner.SSHLogLevel != "" {
		runnerCommand = append(runnerCommand, "--ssh-log-level", c.Runner.SSHLogLevel)
	}
	return append(commands, strings.Join(runnerCommand, " "))
}

func (c *CLIArgs) DockerMounts(hostTaskDir string) ([]mount.Mount, error) {
	return []mount.Mount{
		{
			Type:   mount.TypeBind,
			Source: taskRunnerDir(hostTaskDir),
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
	return []int{c.Runner.HTTPPort, c.Runner.SSHPort}
}

// tasksDirName is the name of the dir inside shim's home dir that holds the dirs of
// the tasks. A task dir holds shim's own files, such as the task state file and the
// image pull log, and the runner dir, the only part of it mounted into the container.
// Historically, the whole task dir was mounted into the container and held runner's
// files only, hence the name, which is kept for backward compatibility: an upgraded
// shim must find the dirs of the tasks created by the previous version.
const tasksDirName = "runners"

// taskRunnerDirName is the name of the dir inside a task dir that is mounted into the
// container as consts.RunnerTempDir. Only the files in this dir are shared with the
// container, the rest of the task dir is private to shim.
const taskRunnerDirName = "runner"

func (c *CLIArgs) TasksDir() string {
	return filepath.Join(c.Shim.HomeDir, tasksDirName)
}

// MakeTaskDir creates the dir of the task, including the runner dir inside it,
// and returns the path to the task dir
func (c *CLIArgs) MakeTaskDir(name string) (string, error) {
	taskDir := filepath.Join(c.TasksDir(), name)
	// Only shim needs access to the task dir itself, unlike the runner dir, which is
	// written by the container
	if err := os.MkdirAll(taskDir, 0o700); err != nil {
		return "", fmt.Errorf("create task directory: %w", err)
	}
	if err := os.MkdirAll(taskRunnerDir(taskDir), 0o755); err != nil {
		return "", fmt.Errorf("create runner directory: %w", err)
	}
	return taskDir, nil
}

// taskRunnerDir returns the path to the runner dir inside the given task dir
func taskRunnerDir(taskDir string) string {
	return filepath.Join(taskDir, taskRunnerDirName)
}
