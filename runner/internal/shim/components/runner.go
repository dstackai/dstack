package components

import (
	"context"
	"errors"
	"fmt"
	"os/exec"
	"strings"
	"sync"

	"github.com/dstackai/dstack/runner/internal/common"
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
		return errors.New("install runner: already installing")
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

func (m *RunnerManager) check(ctx context.Context) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	exists, err := common.PathExists(m.path)
	if err != nil {
		m.status = ComponentStatusError
		m.version = ""
		return fmt.Errorf("check runner: %w", err)
	}
	if !exists {
		m.status = ComponentStatusNotInstalled
		m.version = ""
		return nil
	}

	cmd := exec.CommandContext(ctx, m.path, "--version")
	output, err := cmd.Output()
	if err != nil {
		m.status = ComponentStatusError
		m.version = ""
		return fmt.Errorf("check runner: %w", err)
	}

	rawVersion := string(output) // dstack-runner version 0.19.38
	versionFields := strings.Fields(rawVersion)
	if len(versionFields) != 3 {
		m.status = ComponentStatusError
		m.version = ""
		return fmt.Errorf("check runner: unexpected version output: %s", rawVersion)
	}
	m.status = ComponentStatusInstalled
	m.version = versionFields[2]
	return nil
}
