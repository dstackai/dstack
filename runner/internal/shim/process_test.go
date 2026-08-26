package shim

import (
	"bytes"
	"context"
	"io"
	"testing"

	dockertypes "github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	docker "github.com/docker/docker/client"
	"github.com/docker/docker/errdefs"
	"github.com/docker/docker/pkg/stdcopy"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/dstackai/dstack/runner/internal/common/types"
)

func TestProcessTasks_ContainerIsRunning(t *testing.T) {
	client := &dockerClientMock{containers: []dockertypes.Container{
		taskContainerSummary("task-1", "container-1", containerStateRunning),
	}}
	runner := newTestRunner(t, client)
	addTask(runner, newRunningTask("task-1", "container-1"))

	runner.ProcessTasks(t.Context())

	task, _ := runner.tasks.Get("task-1")
	assert.Equal(t, TaskStatusRunning, task.Status)
	assert.False(t, task.cleanedUp)
}

func TestProcessTasks_ContainerExitedSuccessfully(t *testing.T) {
	client := &dockerClientMock{
		containers: []dockertypes.Container{
			taskContainerSummary("task-1", "container-1", containerStateFinished),
		},
		inspect: map[string]dockertypes.ContainerJSON{
			"container-1": exitedContainer("container-1", 0),
		},
	}
	runner := newTestRunner(t, client)
	addTask(runner, newRunningTask("task-1", "container-1"))

	runner.ProcessTasks(t.Context())

	task, _ := runner.tasks.Get("task-1")
	assert.Equal(t, TaskStatusTerminated, task.Status)
	assert.Equal(t, string(types.TerminationReasonDoneByRunner), task.TerminationReason)
	assert.Empty(t, task.TerminationMessage)
	assert.True(t, task.cleanedUp)
}

func TestProcessTasks_ContainerExitedWithError(t *testing.T) {
	client := &dockerClientMock{
		containers: []dockertypes.Container{
			taskContainerSummary("task-1", "container-1", containerStateFinished),
		},
		inspect: map[string]dockertypes.ContainerJSON{
			"container-1": exitedContainer("container-1", 137),
		},
		logs: map[string]string{"container-1": "out of memory\n"},
	}
	runner := newTestRunner(t, client)
	addTask(runner, newRunningTask("task-1", "container-1"))

	runner.ProcessTasks(t.Context())

	task, _ := runner.tasks.Get("task-1")
	assert.Equal(t, TaskStatusTerminated, task.Status)
	assert.Equal(t, string(types.TerminationReasonContainerExitedWithError), task.TerminationReason)
	assert.Equal(t, "out of memory", task.TerminationMessage)
	assert.True(t, task.cleanedUp)
}

func TestProcessTasks_ContainerNotFound(t *testing.T) {
	client := &dockerClientMock{}
	runner := newTestRunner(t, client)
	addTask(runner, newRunningTask("task-1", "container-1"))

	runner.ProcessTasks(t.Context())

	task, _ := runner.tasks.Get("task-1")
	assert.Equal(t, TaskStatusTerminated, task.Status)
	assert.Equal(t, string(types.TerminationReasonExecutorError), task.TerminationReason)
	assert.Equal(t, "container not found", task.TerminationMessage)
	assert.True(t, task.cleanedUp)
}

// A container that has never been started means that the shim stopped running
// while the task was being started
func TestProcessTasks_ContainerNotStarted(t *testing.T) {
	client := &dockerClientMock{containers: []dockertypes.Container{
		taskContainerSummary("task-1", "container-1", containerStateCreated),
	}}
	runner := newTestRunner(t, client)
	addTask(runner, newRunningTask("task-1", "container-1"))

	runner.ProcessTasks(t.Context())

	task, _ := runner.tasks.Get("task-1")
	assert.Equal(t, TaskStatusTerminated, task.Status)
	assert.Equal(t, string(types.TerminationReasonExecutorError), task.TerminationReason)
	assert.Equal(t, "container was not started", task.TerminationMessage)
	assert.True(t, task.cleanedUp)
	assert.Empty(t, client.inspected)
}

// A failed inspect request must not terminate the task, the next call retries
func TestProcessTasks_InspectError(t *testing.T) {
	client := &dockerClientMock{
		containers: []dockertypes.Container{
			taskContainerSummary("task-1", "container-1", containerStateFinished),
		},
	}
	runner := newTestRunner(t, client)
	addTask(runner, newRunningTask("task-1", "container-1"))

	runner.ProcessTasks(t.Context())

	task, _ := runner.tasks.Get("task-1")
	assert.Equal(t, TaskStatusRunning, task.Status)
	assert.False(t, task.cleanedUp)
}

// Tasks owned by Start() must not be processed, even if their containers exited
func TestProcessTasks_TaskInFlight(t *testing.T) {
	client := &dockerClientMock{
		containers: []dockertypes.Container{
			taskContainerSummary("task-1", "container-1", containerStateFinished),
		},
		inspect: map[string]dockertypes.ContainerJSON{
			"container-1": exitedContainer("container-1", 0),
		},
	}
	runner := newTestRunner(t, client)
	task := newRunningTask("task-1", "container-1")
	task.startInFlight = true
	addTask(runner, task)

	runner.ProcessTasks(t.Context())

	task, _ = runner.tasks.Get("task-1")
	assert.Equal(t, TaskStatusRunning, task.Status)
	assert.False(t, task.cleanedUp)
	assert.Empty(t, client.stopped)
}

func TestProcessTasks_ReleasesGpus(t *testing.T) {
	client := &dockerClientMock{
		containers: []dockertypes.Container{
			taskContainerSummary("task-1", "container-1", containerStateFinished),
		},
		inspect: map[string]dockertypes.ContainerJSON{
			"container-1": exitedContainer("container-1", 0),
		},
	}
	runner := newTestRunner(t, client)
	runner.gpuLock = newTestGpuLock(t, "gpu-0", "gpu-1")
	require.Len(t, runner.gpuLock.Lock(t.Context(), []string{"gpu-0"}), 1)
	task := newRunningTask("task-1", "container-1")
	task.gpuIDs = []string{"gpu-0"}
	addTask(runner, task)

	runner.ProcessTasks(t.Context())

	gpuIDs, err := runner.gpuLock.Acquire(t.Context(), 2)
	assert.NoError(t, err)
	assert.Len(t, gpuIDs, 2)
}

// A container started concurrently with the termination must be stopped
func TestProcessTasks_TerminatedTaskWithRunningContainer(t *testing.T) {
	client := &dockerClientMock{containers: []dockertypes.Container{
		taskContainerSummary("task-1", "container-1", containerStateRunning),
	}}
	runner := newTestRunner(t, client)
	task := newRunningTask("task-1", "container-1")
	task.SetStatusTerminated(string(types.TerminationReasonTerminatedByUser), "")
	addTask(runner, task)

	runner.ProcessTasks(t.Context())

	task, _ = runner.tasks.Get("task-1")
	assert.Equal(t, TaskStatusTerminated, task.Status)
	assert.Equal(t, string(types.TerminationReasonTerminatedByUser), task.TerminationReason)
	assert.Equal(t, []string{"container-1"}, client.stopped)
	assert.True(t, task.cleanedUp)
}

func TestProcessTasks_TerminatedTaskAlreadyCleanedUp(t *testing.T) {
	client := &dockerClientMock{containers: []dockertypes.Container{
		taskContainerSummary("task-1", "container-1", containerStateFinished),
	}}
	runner := newTestRunner(t, client)
	task := newRunningTask("task-1", "container-1")
	task.SetStatusTerminated(string(types.TerminationReasonDoneByRunner), "")
	task.cleanedUp = true
	addTask(runner, task)

	runner.ProcessTasks(t.Context())

	assert.Empty(t, client.stopped)
	assert.Empty(t, client.inspected)
}

/* Utilities */

// containerStateFinished is one of the states of a container that is not running
const containerStateFinished = "exited"

func newTestRunner(t *testing.T, client docker.APIClient) *DockerRunner {
	t.Helper()
	return &DockerRunner{
		client:       client,
		dockerParams: &dockerParametersMock{runnersDir: t.TempDir()},
		gpuLock:      newTestGpuLock(t),
		tasks:        NewTaskStorage(),
	}
}

func newTestGpuLock(t *testing.T, ids ...string) *GpuLock {
	t.Helper()
	lock := make(map[string]bool, len(ids))
	for _, id := range ids {
		lock[id] = false
	}
	return &GpuLock{lock: lock}
}

func newRunningTask(taskID string, containerID string) Task {
	task := NewTask(taskID, TaskStatusRunning)
	task.containerName = taskID + "-name"
	task.containerID = containerID
	return task
}

func addTask(runner *DockerRunner, task Task) {
	runner.tasks.tasks[task.ID] = task
}

func taskContainerSummary(taskID string, containerID string, state string) dockertypes.Container {
	return dockertypes.Container{
		ID:     containerID,
		State:  state,
		Labels: map[string]string{LabelKeyIsTask: LabelValueTrue, LabelKeyTaskID: taskID},
	}
}

func exitedContainer(containerID string, exitCode int) dockertypes.ContainerJSON {
	return dockertypes.ContainerJSON{
		ContainerJSONBase: &dockertypes.ContainerJSONBase{
			ID: containerID,
			State: &dockertypes.ContainerState{
				Status:   containerStateFinished,
				ExitCode: exitCode,
			},
		},
	}
}

/* Mocks */

// dockerClientMock implements the part of the Docker API used to process tasks.
// Calling any other method panics, as the embedded interface is nil
type dockerClientMock struct {
	docker.APIClient

	containers []dockertypes.Container
	inspect    map[string]dockertypes.ContainerJSON
	logs       map[string]string

	inspected []string
	stopped   []string
}

func (c *dockerClientMock) ContainerList(
	_ context.Context, _ container.ListOptions,
) ([]dockertypes.Container, error) {
	return c.containers, nil
}

func (c *dockerClientMock) ContainerInspect(
	_ context.Context, containerID string,
) (dockertypes.ContainerJSON, error) {
	c.inspected = append(c.inspected, containerID)
	inspection, ok := c.inspect[containerID]
	if !ok {
		return dockertypes.ContainerJSON{}, errdefs.NotFound(ErrNotFound)
	}
	return inspection, nil
}

func (c *dockerClientMock) ContainerLogs(
	_ context.Context, containerID string, _ container.LogsOptions,
) (io.ReadCloser, error) {
	logs, ok := c.logs[containerID]
	if !ok {
		return nil, errdefs.NotFound(ErrNotFound)
	}
	// Container logs are multiplexed, see stdcopy.StdCopy()
	buffer := new(bytes.Buffer)
	if _, err := stdcopy.NewStdWriter(buffer, stdcopy.Stdout).Write([]byte(logs)); err != nil {
		return nil, err
	}
	return io.NopCloser(buffer), nil
}

func (c *dockerClientMock) ContainerStop(
	_ context.Context, containerID string, _ container.StopOptions,
) error {
	c.stopped = append(c.stopped, containerID)
	return nil
}
