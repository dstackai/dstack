package api

import (
	"context"
	"sync"

	"github.com/dstackai/dstack/runner/internal/shim"
)

type DummyRunner struct {
	tasks map[string]bool
	mu    sync.Mutex
}

func (ds *DummyRunner) Submit(ctx context.Context, cfg shim.TaskConfig) error {
	ds.mu.Lock()
	defer ds.mu.Unlock()
	if _, ok := ds.tasks[cfg.ID]; ok {
		return shim.ErrRequest
	}
	ds.tasks[cfg.ID] = true
	return nil
}

func (ds *DummyRunner) Run(context.Context, string) error {
	return nil
}

func (ds *DummyRunner) Terminate(context.Context, string, uint, string, string) error {
	return nil
}

func (ds *DummyRunner) Remove(context.Context, string) error {
	return nil
}

func (ds *DummyRunner) TaskList() []*shim.TaskListItem {
	return []*shim.TaskListItem{}
}

func (ds *DummyRunner) TaskInfo(taskID string) shim.TaskInfo {
	return shim.TaskInfo{}
}

func (ds *DummyRunner) Resources(context.Context) shim.Resources {
	return shim.Resources{}
}

func NewDummyRunner() *DummyRunner {
	return &DummyRunner{
		tasks: map[string]bool{},
	}
}
