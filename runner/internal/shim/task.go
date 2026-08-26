package shim

import (
	"context"
	"crypto/sha256"
	"fmt"
	"sync"

	"github.com/dstackai/dstack/runner/internal/common/log"
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
	TerminationReason  string
	TerminationMessage string

	config        TaskConfig
	containerName string
	containerID   string
	cancelPull    context.CancelFunc
	gpuIDs        []string
	ports         []PortMapping
	runnerDir     string // path on host mapped to consts.RunnerDir in container
	// startInFlight is true while Start() is working on the task. Start() owns the
	// task resources until it returns, therefore ProcessTasks() skips such tasks.
	// Tasks restored from containers are never in flight.
	startInFlight bool
	// cleanedUp is true once the resources acquired for the task (host SSH keys,
	// volumes, GPUs) are released. Resources are released only after the container
	// is not running anymore.
	cleanedUp bool

	pullTracker *PullTracker

	mu *sync.Mutex
}

// Lock is used for exclusive operations, e.g, stopping a container,
// removing task data, etc. It blocks until the lock is acquired, since
// contention is expected, e.g., the server may terminate a task while it is
// being processed in the background.
func (t *Task) Lock(ctx context.Context) {
	t.mu.Lock()
	log.Trace(ctx, "locked", "task", t.ID)
}

// TryLock is a non-blocking version of Lock. It reports whether the lock has
// been acquired, so that the caller can retry later instead of waiting.
func (t *Task) TryLock(ctx context.Context) bool {
	if !t.mu.TryLock() {
		log.Trace(ctx, "already locked", "task", t.ID)
		return false
	}
	log.Trace(ctx, "locked", "task", t.ID)
	return true
}

// Release should be called Unlock, but this name triggers govet copylocks check,
// since "thanks" to Go implicit interfaces, a struct with Lock/Unlock method pair
// looks like lock: https://github.com/golang/go/issues/18451
func (t *Task) Release(ctx context.Context) {
	t.mu.Unlock()
	log.Trace(ctx, "unlocked", "task", t.ID)
}

func (t *Task) IsTransitionAllowed(toStatus TaskStatus) bool {
	// same-state transitions are not allowed unless stated otherwise, meaning that
	// two consecutive updates to the same status are not allowed in most cases.
	// This is mainly done to avoid erroneous/concurrent updates.
	// Note that TaskStorage.Modify() checks the transition only if the status changes,
	// therefore committing internal state without changing the status is always allowed.
	switch toStatus {
	case TaskStatusPending:
		// initial status, task should be Add()ed with it, not Modify()ed
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
		// terminated -> terminated is also allowed since server _always_ tries to
		// terminate the task, even if it is already terminated, but this is a special case,
		// see TaskStorage.Modify() for details
		return true
	}
	return false
}

// NB: Some SetStatus* methods also accept and set state fields, but this is for convenience only,
// and does not mean that all state fields are managed that way (quite contrary, most of the fields
// are set directly)

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

func (t *Task) SetStatusRunning() {
	t.Status = TaskStatusRunning
}

func (t *Task) SetStatusTerminated(reason string, message string) {
	t.Status = TaskStatusTerminated
	t.TerminationReason = reason
	t.TerminationMessage = message
	t.cancelPull = nil
}

func NewTask(id string, status TaskStatus, containerName string, containerID string, gpuIDs []string, ports []PortMapping, runnerDir string) Task {
	return Task{
		ID:            id,
		Status:        status,
		containerName: containerName,
		containerID:   containerID,
		runnerDir:     runnerDir,
		gpuIDs:        gpuIDs,
		ports:         ports,
		pullTracker:   newPullTracker(),
		mu:            &sync.Mutex{},
	}
}

func NewTaskFromConfig(cfg TaskConfig) Task {
	return Task{
		ID:            cfg.ID,
		Status:        TaskStatusPending,
		config:        cfg,
		containerName: generateUniqueName(cfg.Name, cfg.ID),
		pullTracker:   newPullTracker(),
		mu:            &sync.Mutex{},
	}
}

type TaskStorage struct {
	// Task.ID: Task mapping
	tasks map[string]Task
	mu    sync.RWMutex
}

// Get a _copy_ of all tasks. To "commit" changes, use Modify()
func (ts *TaskStorage) List() []Task {
	ts.mu.RLock()
	defer ts.mu.RUnlock()
	tasks := make([]Task, 0, len(ts.tasks))
	for _, task := range ts.tasks {
		tasks = append(tasks, task)
	}
	return tasks
}

// Get a _copy_ of the task. To "commit" changes, use Modify()
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

// Modify applies fn to a _copy_ of the _existing_ task and commits the copy,
// returning it on success. If the task is not in the storage, do nothing and
// return ErrNotFound.
// If fn returns an error, or if the resulting status transition is not allowed,
// the copy is discarded, that is, a partially applied fn never reaches the storage.
// The transition is checked only if fn changes the status, therefore fn is free to
// update the internal state of the task without changing its status.
// fn is called with the storage lock held, so it must be fast and must not block,
// in particular, it must not call the Docker API or touch the file system.
func (ts *TaskStorage) Modify(id string, fn func(*Task) error) (Task, error) {
	ts.mu.Lock()
	defer ts.mu.Unlock()
	currentTask, ok := ts.tasks[id]
	if !ok {
		return Task{}, ErrNotFound
	}
	task := currentTask
	if err := fn(&task); err != nil {
		return Task{}, err
	}
	if task.Status != currentTask.Status && !currentTask.IsTransitionAllowed(task.Status) {
		return Task{}, fmt.Errorf("%w: %s -> %s transition not allowed", ErrRequest, currentTask.Status, task.Status)
	}
	if currentTask.Status == TaskStatusTerminated && currentTask.TerminationReason != "" {
		// We ignore reason/message fields if they are already set to avoid
		// overriding these fields by the server, which _always_ tries to terminate the task,
		// even if it is not running
		task.TerminationReason = currentTask.TerminationReason
		task.TerminationMessage = currentTask.TerminationMessage
	}
	ts.tasks[id] = task
	return task, nil
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
