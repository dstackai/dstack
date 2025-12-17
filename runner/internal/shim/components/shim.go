package components

import (
	"context"
	"fmt"
	"sync"
)

type ShimManager struct {
	path    string
	version string
	status  ComponentStatus

	mu *sync.RWMutex
}

func NewShimManager(ctx context.Context, pth string) (*ShimManager, error) {
	m := ShimManager{
		path: pth,
		mu:   &sync.RWMutex{},
	}
	err := m.check(ctx)
	return &m, err
}

func (m *ShimManager) GetInfo(ctx context.Context) ComponentInfo {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return ComponentInfo{
		Name:    ComponentNameShim,
		Version: m.version,
		Status:  m.status,
	}
}

func (m *ShimManager) Install(ctx context.Context, url string, force bool) error {
	m.mu.Lock()
	if m.status == ComponentStatusInstalling {
		m.mu.Unlock()
		return fmt.Errorf("install %s: already installing", ComponentNameShim)
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

func (m *ShimManager) check(ctx context.Context) (err error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	m.status, m.version, err = checkDstackComponent(ctx, ComponentNameShim, m.path)
	return err
}
