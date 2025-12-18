package components

import (
	"context"
	"fmt"
	"sync"
)

type RunnerManager struct {
	path    string
	version string
	status  ComponentStatus

	mu *sync.RWMutex
}

func NewRunnerManager(ctx context.Context, pth string) (*RunnerManager, error) {
	m := RunnerManager{
		path: pth,
		mu:   &sync.RWMutex{},
	}
	err := m.check(ctx)
	return &m, err
}

func (m *RunnerManager) GetInfo(ctx context.Context) ComponentInfo {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return ComponentInfo{
		Name:    ComponentNameRunner,
		Version: m.version,
		Status:  m.status,
	}
}

func (m *RunnerManager) Install(ctx context.Context, url string, force bool) error {
	m.mu.Lock()
	if m.status == ComponentStatusInstalling {
		m.mu.Unlock()
		return fmt.Errorf("install %s: already installing", ComponentNameRunner)
	}
	m.status = ComponentStatusInstalling
	m.version = ""
	m.mu.Unlock()

	downloadErr := downloadFile(ctx, url, m.path, 0o755, force)
	// Recheck the binary even if the download has failed, just in case.
	checkErr := m.check(ctx)
	if downloadErr != nil {
		return downloadErr
	}
	return checkErr
}

func (m *RunnerManager) check(ctx context.Context) (err error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	m.status, m.version, err = checkDstackComponent(ctx, ComponentNameRunner, m.path)
	return err
}
