package shim

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestTaskState_RoundTrip(t *testing.T) {
	dir := t.TempDir()
	task := NewTaskFromConfig(TaskConfig{
		ID:               "task-1",
		Name:             "task",
		RegistryUsername: "user",
		RegistryPassword: "secret",
		HostSshUser:      "root",
		HostSshKeys:      []string{"ssh-ed25519 AAAA"},
		Volumes:          []VolumeInfo{{Name: "volume-1", Backend: "aws"}},
	})
	task.TerminationReason = "terminated_by_user"
	task.TerminationMessage = "bye"
	task.cleanedUp = true

	require.NoError(t, writeTaskState(dir, newTaskState(&task)))

	state, err := readTaskState(dir)
	require.NoError(t, err)
	assert.Equal(t, taskStateVersion, state.Version)
	assert.Equal(t, "task-1", state.ID)
	assert.Equal(t, []VolumeInfo{{Name: "volume-1", Backend: "aws"}}, state.Config.Volumes)
	assert.Equal(t, "root", state.Config.HostSshUser)
	assert.Equal(t, []string{"ssh-ed25519 AAAA"}, state.Config.HostSshKeys)
	assert.Equal(t, "terminated_by_user", state.TerminationReason)
	assert.Equal(t, "bye", state.TerminationMessage)
	assert.True(t, state.CleanedUp)

	// The registry credentials are not persisted, and the task is not affected
	assert.Empty(t, state.Config.RegistryUsername)
	assert.Empty(t, state.Config.RegistryPassword)
	assert.Equal(t, "secret", task.config.RegistryPassword)
	data, err := os.ReadFile(filepath.Join(dir, taskStateFileName))
	require.NoError(t, err)
	assert.NotContains(t, string(data), "secret")

	// The temporary file used to write the state atomically is not left behind
	entries, err := os.ReadDir(dir)
	require.NoError(t, err)
	assert.Len(t, entries, 1)
}

func TestReadTaskState_DoesNotExist(t *testing.T) {
	_, err := readTaskState(t.TempDir())
	assert.ErrorIs(t, err, os.ErrNotExist)
}

func TestReadTaskState_Corrupted(t *testing.T) {
	dir := t.TempDir()
	require.NoError(t, os.WriteFile(filepath.Join(dir, taskStateFileName), []byte("{"), 0o600))

	_, err := readTaskState(dir)
	assert.Error(t, err)
	assert.NotErrorIs(t, err, os.ErrNotExist)
}

func TestReadTaskState_UnsupportedVersion(t *testing.T) {
	dir := t.TempDir()
	state := []byte(`{"version": 999, "id": "task-1"}`)
	require.NoError(t, os.WriteFile(filepath.Join(dir, taskStateFileName), state, 0o600))

	_, err := readTaskState(dir)
	assert.ErrorContains(t, err, "unsupported task state version")
}

func TestSaveTaskState(t *testing.T) {
	runner := newTestRunner(t, nil)
	dir := t.TempDir()
	task := NewTaskFromConfig(TaskConfig{ID: "task-1", Name: "task"})
	task.taskDir = dir
	addTask(runner, task)

	runner.saveTaskState(t.Context(), "task-1")

	state, err := readTaskState(dir)
	require.NoError(t, err)
	assert.Equal(t, "task-1", state.ID)
}

// A task that has not acquired any resources yet has no dir to save the state to
func TestSaveTaskState_NoTaskDir(t *testing.T) {
	runner := newTestRunner(t, nil)
	addTask(runner, NewTaskFromConfig(TaskConfig{ID: "task-1", Name: "task"}))

	runner.saveTaskState(t.Context(), "task-1")

	// The state file must not be written to the current working directory
	assert.NoFileExists(t, taskStateFileName)
}

func TestScanTaskDirs(t *testing.T) {
	tasksDir := t.TempDir()
	dir := makeTaskDir(t, tasksDir, "task-0-0-1234abcd", "task-1")
	// A dir without a state file may belong to anything, e.g., to a task started by a
	// shim version that did not write the state file
	require.NoError(t, os.MkdirAll(filepath.Join(tasksDir, "legacy-0-0-90abef01"), 0o755))
	// Dot dirs are not task dirs
	makeTaskDir(t, tasksDir, ".trash-task-0-0-1234abcd-1", "trashed-task")

	stored := scanTaskDirs(t.Context(), tasksDir)

	require.Len(t, stored, 1)
	require.Contains(t, stored, "task-1")
	assert.Equal(t, dir, stored["task-1"].dir)
	assert.Equal(t, "task-1", stored["task-1"].state.ID)
}

func TestScanTaskDirs_NoTasksDir(t *testing.T) {
	stored := scanTaskDirs(t.Context(), filepath.Join(t.TempDir(), "missing"))

	assert.Empty(t, stored)
}

func TestFindLegacyTaskDir(t *testing.T) {
	runner := newTestRunner(t, nil)
	tasksDir := runner.dockerParams.TasksDir()
	dir := filepath.Join(tasksDir, "legacy-0-0-90abef01")
	require.NoError(t, os.MkdirAll(dir, 0o755))

	assert.Equal(t, dir, runner.findLegacyTaskDir("legacy-0-0-90abef01"))
	assert.Empty(t, runner.findLegacyTaskDir("unknown-0-0-1234abcd"))
	// An empty container name must not resolve to the tasks dir itself
	assert.Empty(t, runner.findLegacyTaskDir(""))
}

func TestSweepOrphanedTaskDirs(t *testing.T) {
	runner := newTestRunner(t, nil)
	tasksDir := runner.dockerParams.TasksDir()

	// A task that has no container: its resources are released and its dir is removed
	orphanedDir := makeTaskDir(t, tasksDir, "orphaned-0-0-1234abcd", "orphaned-task")
	// A task restored from its container: still in use
	restoredDir := makeTaskDir(t, tasksDir, "restored-0-0-5678cdef", "restored-task")
	addTask(runner, newRunningTask("restored-task", "container-1"))

	runner.sweepOrphanedTaskDirs(t.Context(), scanTaskDirs(t.Context(), tasksDir))

	assert.NoDirExists(t, orphanedDir)
	assert.DirExists(t, restoredDir)
}

func makeTaskDir(t *testing.T, tasksDir string, name string, taskID string) string {
	t.Helper()
	dir := filepath.Join(tasksDir, name)
	require.NoError(t, os.MkdirAll(taskRunnerDir(dir), 0o755))
	task := NewTaskFromConfig(TaskConfig{ID: taskID, Name: name})
	require.NoError(t, writeTaskState(dir, newTaskState(&task)))
	return dir
}
