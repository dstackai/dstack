package shim

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/dstackai/dstack/runner/internal/common/log"
)

// taskStateFileName is the name of the task state file in the task dir
const taskStateFileName = "task.json"

// taskStateVersion is the version of the task state file format. It is only bumped on
// incompatible changes: new fields are ignored by older versions of the shim, and are
// zero when an older file is read by a newer version.
const taskStateVersion = 1

// taskState is the part of the task state that cannot be recovered from the task
// container, persisted so that the task can be finalized by another shim process.
// Everything that is recoverable -- the container ID, the GPUs, the ports -- is left
// out, keeping the container the source of truth for it.
type taskState struct {
	Version int    `json:"version"`
	ID      string `json:"id"`
	// Config is the task config with the registry credentials stripped: they are only
	// needed to pull the image, which is already pulled by the time the state is read.
	// The rest is kept for cleanup -- volumes and host SSH keys in particular.
	Config TaskConfig `json:"config"`
	// TerminationReason is empty unless the task has been terminated, meaning that the
	// outcome is to be determined from the container state
	TerminationReason  string `json:"termination_reason"`
	TerminationMessage string `json:"termination_message"`
	CleanedUp          bool   `json:"cleaned_up"`
}

func newTaskState(task *Task) taskState {
	config := task.config
	config.RegistryUsername = ""
	config.RegistryPassword = ""
	return taskState{
		Version:            taskStateVersion,
		ID:                 task.ID,
		Config:             config,
		TerminationReason:  task.TerminationReason,
		TerminationMessage: task.TerminationMessage,
		CleanedUp:          task.cleanedUp,
	}
}

// saveTaskState writes the state of the task to its task dir. Tasks that have not
// acquired any resources yet, that is, tasks without a task dir, are skipped.
// The stored task is snapshotted while holding a lock, so that a concurrent call
// cannot replace a newer state with an older one.
func (d *DockerRunner) saveTaskState(ctx context.Context, taskID string) {
	d.stateMu.Lock()
	defer d.stateMu.Unlock()
	task, ok := d.tasks.Get(taskID)
	if !ok || task.taskDir == "" {
		return
	}
	if err := writeTaskState(task.taskDir, newTaskState(&task)); err != nil {
		log.Error(ctx, "failed to save task state", "task", taskID, "err", err)
	}
}

func writeTaskState(dir string, state taskState) error {
	data, err := json.Marshal(state)
	if err != nil {
		return fmt.Errorf("marshal task state: %w", err)
	}
	data = append(data, '\n')
	path := filepath.Join(dir, taskStateFileName)
	// Written to a temporary file and renamed, so that a state file is never partial
	tempPath := path + ".tmp"
	if err := writeFileSync(tempPath, data, 0o600); err != nil {
		return fmt.Errorf("write task state: %w", err)
	}
	if err := os.Rename(tempPath, path); err != nil {
		return fmt.Errorf("rename task state: %w", err)
	}
	return nil
}

// readTaskState reads the state file from the task dir. The error wraps os.ErrNotExist
// if the dir has no state file, e.g., if the task was started by a shim version that
// did not write one.
func readTaskState(dir string) (taskState, error) {
	var state taskState
	path := filepath.Join(dir, taskStateFileName)
	data, err := os.ReadFile(path)
	if err != nil {
		return state, fmt.Errorf("read task state: %w", err)
	}
	if err := json.Unmarshal(data, &state); err != nil {
		return state, fmt.Errorf("unmarshal task state %s: %w", path, err)
	}
	if state.Version != taskStateVersion {
		return state, fmt.Errorf("unsupported task state version %d in %s", state.Version, path)
	}
	return state, nil
}

// storedTask is a task state file found in the tasks dir, along with the task dir it
// was read from
type storedTask struct {
	dir   string
	state taskState
}

// scanTaskDirs reads the state files of all the task dirs, returning them by task ID.
// This is how the dirs of the tasks started by a previous shim process are found, both
// the dirs of the tasks restored from their containers and the dirs of the orphaned
// tasks swept by sweepOrphanedTaskDirs().
// Dirs without a state file are skipped, as there is no way to tell whether they belong
// to a task; the dirs of the tasks started by a shim version that did not write state
// files are found by findLegacyTaskDir() instead.
func scanTaskDirs(ctx context.Context, tasksDir string) map[string]storedTask {
	stored := make(map[string]storedTask)
	entries, err := os.ReadDir(tasksDir)
	if err != nil {
		if !errors.Is(err, os.ErrNotExist) {
			log.Error(ctx, "failed to list task dirs", "dir", tasksDir, "err", err)
		}
		return stored
	}
	for _, entry := range entries {
		// Dot dirs are not task dirs, e.g., the .trash-* dirs left by Remove()
		if !entry.IsDir() || strings.HasPrefix(entry.Name(), ".") {
			continue
		}
		dir := filepath.Join(tasksDir, entry.Name())
		state, err := readTaskState(dir)
		if err != nil {
			if !errors.Is(err, os.ErrNotExist) {
				log.Error(ctx, "failed to read task state", "dir", dir, "err", err)
			}
			continue
		}
		if other, ok := stored[state.ID]; ok {
			log.Error(
				ctx, "duplicate task state, ignoring",
				"task", state.ID, "dir", dir, "used", other.dir,
			)
			continue
		}
		stored[state.ID] = storedTask{dir: dir, state: state}
	}
	return stored
}

// findLegacyTaskDir returns the dir of a task started by a shim version that did not
// write state files, so that the dir is still removed along with the task. Such a dir
// cannot be found by scanTaskDirs() and is identified by its name, which is the name of
// the task container. Returns an empty string if there is no such dir.
func (d *DockerRunner) findLegacyTaskDir(containerName string) string {
	if containerName == "" {
		return ""
	}
	dir := filepath.Join(d.dockerParams.TasksDir(), containerName)
	if info, err := os.Stat(dir); err != nil || !info.IsDir() {
		return ""
	}
	return dir
}

// sweepOrphanedTaskDirs releases the resources of the scanned tasks that have no
// container, which normally means that the shim stopped running before the container
// was created, and removes their dirs. The dirs of the tasks restored from their
// containers are left intact.
func (d *DockerRunner) sweepOrphanedTaskDirs(ctx context.Context, storedTasks map[string]storedTask) {
	for taskID, stored := range storedTasks {
		if _, ok := d.tasks.Get(taskID); ok {
			// the task has been restored from its container
			continue
		}
		log.Warning(ctx, "cleaning up orphaned task dir", "task", taskID, "dir", stored.dir)
		if !stored.state.CleanedUp {
			// GPU locks are in-memory, so there is nothing to release: a task without
			// a container holds no GPUs after a restart
			releaseTaskResources(ctx, stored.state.Config)
		}
		if err := os.RemoveAll(stored.dir); err != nil {
			log.Error(ctx, "failed to remove orphaned task dir", "dir", stored.dir, "err", err)
		}
	}
}

// writeFileSync writes the file and flushes it to the disk, so that its content is not
// lost if the host restarts
func writeFileSync(path string, data []byte, perm os.FileMode) (err error) {
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, perm)
	if err != nil {
		return err
	}
	defer func() {
		if closeErr := file.Close(); err == nil {
			err = closeErr
		}
	}()
	if _, err := file.Write(data); err != nil {
		return err
	}
	return file.Sync()
}
