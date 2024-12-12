package shim

import (
	"context"
	"crypto/sha256"
	"fmt"
	"sync"
)

type TaskStatus string

const (
	// pending -> pulling -> creating -> running -> terminated
	//    |         |           |
	//    v         v           v
	// terminated terminated terminated
	TaskStatusPending    TaskStatus = "pending"
	TaskStatusPulling    TaskStatus = "pulling"
	TaskStatusCreating   TaskStatus = "creating"
	TaskStatusRunning    TaskStatus = "running"
	TaskStatusTerminated TaskStatus = "terminated"
)

// Task represents shim-specific part of dstack server's Job entity,
// both configuration submitted by the server (container image,
// container user, etc.) and state managed by the shim (container ID,
// status, etc.)
type Task struct {
	ID                 string
	Status             TaskStatus
	TerminationReason  string // TODO: enum
	TerminationMessage string

	config        TaskConfig
	containerName string
	containerID   string
	cancelPull    context.CancelFunc
}

func (t *Task) SetStatusPulling(cancelPull context.CancelFunc) {
	t.Status = TaskStatusPulling
	t.cancelPull = cancelPull
}

func (t *Task) SetStatusCreating() {
	t.Status = TaskStatusCreating
	t.cancelPull = nil
}

func (t *Task) SetStatusRunning(containerID string) {
	t.Status = TaskStatusRunning
	t.containerID = containerID
}

func (t *Task) SetStatusTerminated(reason string, message string) {
	t.Status = TaskStatusTerminated
	t.TerminationReason = reason
	t.TerminationMessage = message
	t.cancelPull = nil
}

func NewTask(cfg TaskConfig) Task {
	return Task{
		ID:            cfg.ID,
		Status:        TaskStatusPending,
		config:        cfg,
		containerName: generateUniqueName(cfg.Name, cfg.ID),
	}
}

type TaskStorage struct {
	// Task.ID: Task mapping
	tasks map[string]Task
	mu    sync.RWMutex
}

// Get a _copy_ of the task. To "commit" changes, use Update()
func (ts *TaskStorage) Get(id string) (Task, bool) {
	ts.mu.RLock()
	defer ts.mu.RUnlock()
	task, ok := ts.tasks[id]
	return task, ok
}

// Add a _new_ task. If the task is already in the storage, do nothing and return false
func (ts *TaskStorage) Add(task Task) bool {
	ts.mu.Lock()
	defer ts.mu.Unlock()
	if _, ok := ts.tasks[task.ID]; ok {
		return false
	}
	ts.tasks[task.ID] = task
	return true
}

// Update the _existing_ task. If the task is not in the storage, do nothing and return false
func (ts *TaskStorage) Update(task Task) bool {
	ts.mu.Lock()
	defer ts.mu.Unlock()
	if _, ok := ts.tasks[task.ID]; !ok {
		return false
	}
	ts.tasks[task.ID] = task
	return true
}

func (ts *TaskStorage) Delete(id string) {
	ts.mu.Lock()
	defer ts.mu.Unlock()
	delete(ts.tasks, id)
}

func NewTaskStorage() TaskStorage {
	return TaskStorage{
		tasks: make(map[string]Task),
	}
}

// generateUniqueName returns a unique name in the form of <name>-<suffix>,
// where <name> is non-unique human-readable name provided by the server, and
// <suffix> is a relatively short unique hex string generated from (name, id) pair
func generateUniqueName(name string, id string) string {
	suffix := generateNameSuffix(name, id)
	return fmt.Sprintf("%s-%s", name, suffix)
}

// generateNameSuffix returns a (semi-)unique hex string based on (name, id) pair
// Used to avoid possible name clashes
// The generated string is unique as long as
// - (name, id) pair is unique
// - there is no collision within first nameSuffixLen / 2 bytes of hash
func generateNameSuffix(name string, id string) string {
	const nameSuffixLen = 8
	b := []byte(fmt.Sprintf("%s/%s", name, id))
	return fmt.Sprintf("%x", sha256.Sum256(b))[:nameSuffixLen]
}
