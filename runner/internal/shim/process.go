package shim

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/docker/docker/api/types/container"

	"github.com/dstackai/dstack/runner/internal/common/log"
	"github.com/dstackai/dstack/runner/internal/common/types"
)

// Container states reported by the Docker API. The states not listed here, that is,
// exited, dead, and removing, are handled the same way -- as a finished container
// https://github.com/moby/moby/blob/v26.0.0/container/state.go#L120-L145
const (
	containerStateCreated    = "created"
	containerStateRunning    = "running"
	containerStatePaused     = "paused"
	containerStateRestarting = "restarting"
)

// taskContainer is the part of the container list response used to process tasks.
// The list response has no exit code field -- it only reports the exit code as a part
// of a human-readable status string -- therefore a container that is not running
// anymore is inspected separately.
type taskContainer struct {
	id string
	// created, running, paused, restarting, removing, exited, or dead
	state string
}

func (c *taskContainer) isRunning() bool {
	return c.state == containerStateRunning ||
		c.state == containerStatePaused ||
		c.state == containerStateRestarting
}

// ProcessTasks brings the state of tasks in line with the state of their containers:
// tasks whose containers are not running anymore are terminated, and the resources
// of terminated tasks are released.
// Since containers outlive the shim process, this is how tasks are completed after a
// shim restart, in addition to the normal case of a container exiting while the shim
// is running.
// It is expected to be called periodically. Errors are only logged, as the caller can
// do nothing but retry.
func (d *DockerRunner) ProcessTasks(ctx context.Context) {
	var taskIDs []string
	for _, task := range d.tasks.List() {
		if task.startInFlight {
			// Start() owns the task and its resources until it returns
			continue
		}
		switch task.Status {
		case TaskStatusRunning, TaskStatusTerminated:
			taskIDs = append(taskIDs, task.ID)
		case TaskStatusPending, TaskStatusPreparing, TaskStatusPulling, TaskStatusCreating:
			// Start() is about to be called or is already in flight
		}
	}
	if len(taskIDs) == 0 {
		return
	}
	// One list request is enough for all tasks: the container state it reports tells
	// whether the container is still running, which is all that is needed in the
	// most common case
	containers, err := d.listTaskContainers(ctx)
	if err != nil {
		if !errors.Is(err, context.Canceled) {
			// the context is cancelled on shutdown, which is not an error
			log.Error(ctx, "cannot process tasks", "err", err)
		}
		return
	}
	for _, taskID := range taskIDs {
		d.processTask(ctx, taskID, containers)
	}
}

func (d *DockerRunner) processTask(ctx context.Context, taskID string, containers map[string]*taskContainer) {
	task, ok := d.tasks.Get(taskID)
	if !ok {
		return
	}
	// This copy of the task is only used to hold the lock, all copies of a task share
	// the same lock
	if !task.TryLock(ctx) {
		// The task is busy, e.g., being terminated or removed. Try again on the next call
		log.Trace(ctx, "skip processing: task is busy", "task", taskID)
		return
	}
	defer func() { task.Release(ctx) }()
	// The task may have been updated while we were acquiring the lock
	currentTask, ok := d.tasks.Get(taskID)
	if !ok || currentTask.startInFlight {
		return
	}
	switch currentTask.Status {
	case TaskStatusRunning:
		d.processRunningTask(ctx, &currentTask, containers[taskID])
	case TaskStatusTerminated:
		d.processTerminatedTask(ctx, &currentTask, containers[taskID])
	case TaskStatusPending, TaskStatusPreparing, TaskStatusPulling, TaskStatusCreating:
		// not processed, see ProcessTasks()
	}
}

// processRunningTask terminates the task if its container is not running anymore,
// reporting the container exit code as the termination reason.
// The task lock must be held by the caller.
func (d *DockerRunner) processRunningTask(ctx context.Context, task *Task, container *taskContainer) {
	if container == nil {
		// The container has been removed by someone else, e.g., manually
		log.Warning(ctx, "container of running task not found", "task", task.ID)
		d.finalizeLocked(ctx, task, types.TerminationReasonExecutorError, "container not found")
		return
	}
	if container.isRunning() {
		return
	}
	if container.state == containerStateCreated {
		// The container has never been started, which normally means that the shim
		// stopped running between creating and starting it
		log.Warning(ctx, "container of running task is not started", "task", task.ID)
		d.finalizeLocked(ctx, task, types.TerminationReasonExecutorError, "container was not started")
		return
	}
	// The container is finished. Its exit code is not reported by the list request,
	// hence the inspect request
	inspection, err := d.client.ContainerInspect(ctx, container.id)
	if err != nil {
		// Try again on the next call, the task is still considered running
		log.Error(ctx, "failed to inspect container", "task", task.ID, "id", container.id, "err", err)
		return
	}
	if inspection.State == nil {
		log.Error(ctx, "container has no state", "task", task.ID, "id", container.id)
		return
	}
	exitCode := inspection.State.ExitCode
	log.Debug(ctx, "container is not running", "task", task.ID, "state", container.state, "code", exitCode)
	if exitCode == 0 {
		d.finalizeLocked(ctx, task, types.TerminationReasonDoneByRunner, "")
		return
	}
	var message string
	if lastLogs, err := getContainerLastLogs(ctx, d.client, container.id, 5); err == nil {
		message = strings.Join(lastLogs, "\n")
	} else {
		log.Error(ctx, "getContainerLastLogs error", "err", err)
	}
	d.finalizeLocked(ctx, task, types.TerminationReasonContainerExitedWithError, message)
}

// processTerminatedTask releases the resources of an already terminated task.
// The container is stopped first if it is still running, which normally means that
// the task has been terminated while its container was being started.
// The task lock must be held by the caller.
func (d *DockerRunner) processTerminatedTask(ctx context.Context, task *Task, container *taskContainer) {
	if task.cleanedUp {
		return
	}
	if container != nil && container.isRunning() {
		log.Warning(ctx, "stopping container of terminated task", "task", task.ID, "id", container.id)
		if err := d.stopContainer(ctx, container.id, 0); err != nil {
			// Try again on the next call, the resources are not released until then
			log.Error(ctx, "failed to stop container", "task", task.ID, "id", container.id, "err", err)
			return
		}
	}
	d.cleanupLocked(ctx, task)
}

// finalizeLocked releases the task resources and terminates the task.
// The task lock must be held by the caller.
func (d *DockerRunner) finalizeLocked(
	ctx context.Context, task *Task, reason types.TerminationReason, message string,
) {
	d.cleanupLocked(ctx, task)
	if err := d.commit(task, func(t *Task) {
		t.SetStatusTerminated(string(reason), message)
	}); err != nil {
		log.Error(ctx, "failed to commit terminated status", "task", task.ID, "err", err)
		return
	}
	log.Info(ctx, "terminated", "task", task.ID, "reason", reason)
}

func (d *DockerRunner) listTaskContainers(ctx context.Context) (map[string]*taskContainer, error) {
	listOptions := container.ListOptions{All: true, Filters: taskContainerFilters()}
	containers, err := d.client.ContainerList(ctx, listOptions)
	if err != nil {
		return nil, fmt.Errorf("failed to get container list: %w", err)
	}
	taskContainers := make(map[string]*taskContainer, len(containers))
	for _, containerShort := range containers {
		taskID := containerShort.Labels[LabelKeyTaskID]
		if taskID == "" {
			log.Error(ctx, "container has no label", "id", containerShort.ID, "label", LabelKeyTaskID)
			continue
		}
		taskContainers[taskID] = &taskContainer{id: containerShort.ID, state: containerShort.State}
	}
	return taskContainers, nil
}
