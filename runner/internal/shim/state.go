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

// taskStateFileName is the name of the task state file in the task runner dir
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

// saveTaskState writes the state of the task to its runner dir. Tasks that have not
// acquired any resources yet, that is, tasks without a runner dir, are skipped.
// The stored task is snapshotted while holding a lock, so that a concurrent call
// cannot replace a newer state with an older one.
func (d *DockerRunner) saveTaskState(ctx context.Context, taskID string) {
	d.stateMu.Lock()
	defer d.stateMu.Unlock()
	task, ok := d.tasks.Get(taskID)
	if !ok || task.runnerDir == "" {
		return
	}
	if err := writeTaskState(task.runnerDir, newTaskState(&task)); err != nil {
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

// readTaskState reads the state file from the task runner dir. The error wraps
// os.ErrNotExist if the dir has no state file, e.g., if the task was started by a shim
// version that did not write one.
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

// readRestoredTaskState reads the state file of a task being restored from its
// container. It reports whether there was a state file to restore from; if there was
// not, the returned state is empty and the caller has to fall back to the container
func readRestoredTaskState(ctx context.Context, taskID string, runnerDir string) (taskState, bool) {
	if runnerDir == "" {
		return taskState{}, false
	}
	state, err := readTaskState(runnerDir)
	if err != nil {
		if !errors.Is(err, os.ErrNotExist) {
			// A task started by a shim version that did not write the state file has none
			log.Error(ctx, "failed to read task state", "task", taskID, "err", err)
		}
		return taskState{}, false
	}
	if state.ID != taskID {
		log.Error(ctx, "task state belongs to another task", "task", taskID, "id", state.ID)
		return taskState{}, false
	}
	return state, true
}

// sweepOrphanedTaskDirs releases the resources of tasks that have a state file but no
// container, which normally means that the shim stopped running before the container
// was created, and removes their dirs.
// Dirs without a state file are left intact, as there is no way to tell whether they
// belong to a task, and so are the dirs of the tasks restored from containers.
func (d *DockerRunner) sweepOrphanedTaskDirs(ctx context.Context) {
	runnersDir := d.dockerParams.RunnersDir()
	entries, err := os.ReadDir(runnersDir)
	if err != nil {
		if !errors.Is(err, os.ErrNotExist) {
			log.Error(ctx, "failed to list task dirs", "dir", runnersDir, "err", err)
		}
		return
	}
	for _, entry := range entries {
		// Dot dirs are not task dirs, e.g., the .trash-* dirs left by Remove()
		if !entry.IsDir() || strings.HasPrefix(entry.Name(), ".") {
			continue
		}
		dir := filepath.Join(runnersDir, entry.Name())
		state, err := readTaskState(dir)
		if err != nil {
			if !errors.Is(err, os.ErrNotExist) {
				log.Error(ctx, "failed to read task state", "dir", dir, "err", err)
			}
			continue
		}
		if _, ok := d.tasks.Get(state.ID); ok {
			// the task has been restored from its container
			continue
		}
		log.Warning(ctx, "cleaning up orphaned task dir", "task", state.ID, "dir", dir)
		if !state.CleanedUp {
			// GPU locks are in-memory, so there is nothing to release: a task without
			// a container holds no GPUs after a restart
			releaseTaskResources(ctx, state.Config)
		}
		if err := os.RemoveAll(dir); err != nil {
			log.Error(ctx, "failed to remove orphaned task dir", "dir", dir, "err", err)
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
