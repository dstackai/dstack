package shim

import (
	"context"
	"crypto/sha256"
	"fmt"
	"sync"

	"github.com/dstackai/dstack/runner/internal/log"
)

type TaskStatus string

const (
	// pending -> preparing -> pulling -> creating -> running -> terminated
	//    |         |           |            |
	//    v         v           v            v
	// terminated terminated terminated terminated
	TaskStatusPending    TaskStatus = "pending"
	TaskStatusPreparing  TaskStatus = "preparing"
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
	gpuIDs        []string
	runnerDir     string // path on host mapped to consts.RunnerDir in container

	mu *sync.Mutex
}

// Lock is used for exclusive operations, e.g, stopping a container,
// removing task data, etc.
func (t *Task) Lock(ctx context.Context) {
	if !t.mu.TryLock() {
		log.Fatal(ctx, "already locked!", "task", t.ID)
	}
	log.Debug(ctx, "locked", "task", t.ID)
}

// Release should be called Unlock, but this name triggers govet copylocks check,
// since "thanks" to Go implicit interfaces, a struct with Lock/Unlock method pair
// looks like lock: https://github.com/golang/go/issues/18451
func (t *Task) Release(ctx context.Context) {
	t.mu.Unlock()
	log.Debug(ctx, "unlocked", "task", t.ID)
}

func (t *Task) IsTransitionAllowed(toStatus TaskStatus) bool {
	if t.Status == TaskStatusTerminated {
		// terminal status, cannot transition further
		return false
	}
	switch toStatus {
	case TaskStatusPending:
		// initial status, task should be Add()ed with it, not Update()d
		return false
	case TaskStatusPreparing:
		return t.Status == TaskStatusPending
	case TaskStatusPulling:
		return t.Status == TaskStatusPreparing
	case TaskStatusCreating:
		return t.Status == TaskStatusPulling
	case TaskStatusRunning:
		return t.Status == TaskStatusCreating
	case TaskStatusTerminated:
		// we already checked terminated -> terminated (not allowed),
		// all other transitions are allowed
		return true
	}
	return false
}

func (t *Task) SetStatusPreparing() {
	t.Status = TaskStatusPreparing
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

func NewTask(id string, status TaskStatus, containerName string, containerID string, gpuIDs []string, runnerDir string) Task {
	return Task{
		ID:            id,
		Status:        status,
		containerName: containerName,
		containerID:   containerID,
		runnerDir:     runnerDir,
		gpuIDs:        gpuIDs,
		mu:            &sync.Mutex{},
	}
}

func NewTaskFromConfig(cfg TaskConfig) Task {
	return Task{
		ID:            cfg.ID,
		Status:        TaskStatusPending,
		config:        cfg,
		containerName: generateUniqueName(cfg.Name, cfg.ID),
		mu:            &sync.Mutex{},
	}
}

type TaskStorage struct {
	// Task.ID: Task mapping
	tasks map[string]Task
	mu    sync.RWMutex
}

func (ts *TaskStorage) IDs() []string {
	ts.mu.RLock()
	defer ts.mu.RUnlock()
	ids := make([]string, 0, len(ts.tasks))
	for id := range ts.tasks {
		ids = append(ids, id)
	}
	return ids
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
// If the current status is terminated, do nothing and return false
func (ts *TaskStorage) Update(task Task) error {
	ts.mu.Lock()
	defer ts.mu.Unlock()
	currentTask, ok := ts.tasks[task.ID]
	if !ok {
		return ErrNotFound
	}
	if !currentTask.IsTransitionAllowed(task.Status) {
		return fmt.Errorf("%w: %s -> %s transition not allowed", ErrRequest, currentTask.Status, task.Status)
	}
	ts.tasks[task.ID] = task
	return nil
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
