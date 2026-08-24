package shim

import (
	"errors"
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestTaskStorage_Get(t *testing.T) {
	storage := NewTaskStorage()
	storedTask := Task{ID: "1", Status: TaskStatusRunning}
	storage.tasks["1"] = storedTask

	task, ok := storage.Get("1")
	assert.True(t, ok)
	assert.Equal(t, storedTask, task)

	task, ok = storage.Get("2")
	assert.False(t, ok)
	assert.NotEqual(t, storedTask, task)
}

func TestTaskStorage_Add_OK(t *testing.T) {
	storage := NewTaskStorage()
	storedTask := Task{ID: "1", Status: TaskStatusRunning}
	storage.tasks["1"] = storedTask
	addedTask := Task{ID: "2", Status: TaskStatusPending}

	ok := storage.Add(addedTask)
	assert.True(t, ok)
	assert.Equal(t, storedTask, storage.tasks["1"])
	assert.Equal(t, addedTask, storage.tasks["2"])
}

func TestTaskStorage_Add_AlreadyExists(t *testing.T) {
	storage := NewTaskStorage()
	storedTask := Task{ID: "1", Status: TaskStatusRunning}
	storage.tasks["1"] = storedTask

	ok := storage.Add(Task{ID: "1", Status: TaskStatusPending})
	assert.False(t, ok)
	assert.Equal(t, storedTask, storage.tasks["1"])
}

func TestTaskStorage_Modify_OK(t *testing.T) {
	storage := NewTaskStorage()
	storage.tasks["1"] = Task{ID: "1", Status: TaskStatusRunning}

	task, err := storage.Modify("1", func(t *Task) error {
		t.SetStatusTerminated("container_exited_with_error", "oom")
		return nil
	})
	assert.NoError(t, err)
	assert.Equal(t, TaskStatusTerminated, task.Status)
	assert.Equal(t, "container_exited_with_error", task.TerminationReason)
	assert.Equal(t, task, storage.tasks["1"])
}

// The transition is not checked unless the status changes, so that the internal
// state of a task can be committed at any time
func TestTaskStorage_Modify_NoStatusChange(t *testing.T) {
	storage := NewTaskStorage()
	storage.tasks["1"] = Task{ID: "1", Status: TaskStatusRunning}
	ports := []PortMapping{{Host: 30000, Container: 10999}}

	task, err := storage.Modify("1", func(t *Task) error {
		t.ports = ports
		return nil
	})
	assert.NoError(t, err)
	assert.Equal(t, TaskStatusRunning, task.Status)
	assert.Equal(t, ports, storage.tasks["1"].ports)
}

func TestTaskStorage_Modify_DoesNotExist(t *testing.T) {
	storage := NewTaskStorage()

	_, err := storage.Modify("1", func(t *Task) error {
		t.SetStatusPreparing()
		return nil
	})
	assert.ErrorIs(t, err, ErrNotFound)
	assert.Empty(t, storage.tasks)
}

func TestTaskStorage_Modify_TransitionNotAllowed(t *testing.T) {
	storage := NewTaskStorage()
	storedTask := Task{ID: "1", Status: TaskStatusPending}
	storage.tasks["1"] = storedTask

	_, err := storage.Modify("1", func(t *Task) error {
		t.SetStatusRunning()
		return nil
	})
	assert.ErrorIs(t, err, ErrRequest)
	assert.ErrorContains(t, err, fmt.Sprintf("%s -> %s", TaskStatusPending, TaskStatusRunning))
	assert.Equal(t, storedTask, storage.tasks["1"])
}

// A partially applied function must not reach the storage
func TestTaskStorage_Modify_Error(t *testing.T) {
	storage := NewTaskStorage()
	storedTask := Task{ID: "1", Status: TaskStatusPulling}
	storage.tasks["1"] = storedTask
	errFailed := errors.New("failed")

	_, err := storage.Modify("1", func(t *Task) error {
		t.SetStatusCreating()
		return errFailed
	})
	assert.ErrorIs(t, err, errFailed)
	assert.Equal(t, storedTask, storage.tasks["1"])
}

func TestTaskStorage_Modify_TerminationReasonNotOverridden(t *testing.T) {
	storage := NewTaskStorage()
	storage.tasks["1"] = Task{
		ID:                 "1",
		Status:             TaskStatusTerminated,
		TerminationReason:  "container_exited_with_error",
		TerminationMessage: "oom",
	}

	task, err := storage.Modify("1", func(t *Task) error {
		t.SetStatusTerminated("terminated_by_server", "")
		return nil
	})
	assert.NoError(t, err)
	assert.Equal(t, "container_exited_with_error", task.TerminationReason)
	assert.Equal(t, "oom", task.TerminationMessage)
	assert.Equal(t, "container_exited_with_error", storage.tasks["1"].TerminationReason)
}

func TestTaskStorage_Delete(t *testing.T) {
	storage := NewTaskStorage()
	storage.tasks["1"] = Task{ID: "1", Status: TaskStatusRunning}

	storage.Delete("2")
	assert.Equal(t, 1, len(storage.tasks))

	storage.Delete("1")
	assert.Equal(t, 0, len(storage.tasks))
}

func TestTask_TryLock(t *testing.T) {
	ctx := t.Context()
	task := Task{ID: "1", mu: &sync.Mutex{}}

	assert.True(t, task.TryLock(ctx))
	assert.False(t, task.TryLock(ctx))

	task.Release(ctx)
	assert.True(t, task.TryLock(ctx))
}

func TestTask_Lock_WaitsForRelease(t *testing.T) {
	ctx := t.Context()
	task := Task{ID: "1", mu: &sync.Mutex{}}
	task.Lock(ctx)

	locked := make(chan struct{})
	go func() {
		task.Lock(ctx)
		close(locked)
	}()

	select {
	case <-locked:
		t.Fatal("Lock did not wait for Release")
	case <-time.After(50 * time.Millisecond):
	}

	task.Release(ctx)
	select {
	case <-locked:
	case <-time.After(5 * time.Second):
		t.Fatal("Lock did not acquire the lock after Release")
	}
}

func TestTask_IsTransitionAllowed_true(t *testing.T) {
	testCases := []struct {
		oldStatus, newStatus TaskStatus
	}{
		{TaskStatusPending, TaskStatusPreparing},
		{TaskStatusPending, TaskStatusTerminated},
		{TaskStatusPreparing, TaskStatusPulling},
		{TaskStatusPreparing, TaskStatusTerminated},
		{TaskStatusPulling, TaskStatusCreating},
		{TaskStatusPulling, TaskStatusTerminated},
		{TaskStatusCreating, TaskStatusRunning},
		{TaskStatusCreating, TaskStatusTerminated},
		{TaskStatusRunning, TaskStatusTerminated},
		{TaskStatusTerminated, TaskStatusTerminated},
	}
	for _, tc := range testCases {
		task := Task{ID: "1", Status: tc.oldStatus}
		assert.True(t, task.IsTransitionAllowed(tc.newStatus), "%s -> %s", tc.oldStatus, tc.newStatus)
	}
}

func TestTask_IsTransitionAllowed_false(t *testing.T) {
	testCases := []struct {
		oldStatus, newStatus TaskStatus
	}{
		// non-exhaustive list of impossible transitions
		{TaskStatusPending, TaskStatusPending},
		{TaskStatusPending, TaskStatusRunning},
		{TaskStatusPulling, TaskStatusPending},
		{TaskStatusRunning, TaskStatusRunning},
	}
	for _, tc := range testCases {
		task := Task{ID: "1", Status: tc.oldStatus}
		assert.False(t, task.IsTransitionAllowed(tc.newStatus), "%s -> %s", tc.oldStatus, tc.newStatus)
	}
}

func TestNewTaskFromConfig(t *testing.T) {
	cfg := TaskConfig{
		ID:   "66a886db-86db-4cf9-8c06-8984ad15dde2",
		Name: "vllm-0-0",
	}
	task := NewTaskFromConfig(cfg)

	assert.Equal(t, "66a886db-86db-4cf9-8c06-8984ad15dde2", task.ID)
	assert.Equal(t, "vllm-0-0-cff1b8da", task.containerName)
	assert.Equal(t, TaskStatusPending, task.Status)
	assert.Equal(t, cfg, task.config)
}

func TestGenerateUniqueName(t *testing.T) {
	testCases := []struct {
		name, id, expected string
	}{
		{"vllm-0-0", "66a886db-86db-4cf9-8c06-8984ad15dde2", "vllm-0-0-cff1b8da"},
		{"vllm-0-0", "41728e34-bf7e-41da-bf0e-0f46764b1752", "vllm-0-0-bb2a28c3"},
		{"llamacpp-0-0", "66a886db-86db-4cf9-8c06-8984ad15dde2", "llamacpp-0-0-58d1283d"},
	}
	for _, tc := range testCases {
		generated := generateUniqueName(tc.name, tc.id)
		assert.Equal(t, tc.expected, generated)
	}
}
