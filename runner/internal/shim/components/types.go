package components

import "context"

type ComponentName string

const (
	ComponentNameRunner ComponentName = "dstack-runner"
	ComponentNameShim   ComponentName = "dstack-shim"
)

type ComponentStatus string

const (
	ComponentStatusNotInstalled ComponentStatus = "not-installed"
	ComponentStatusInstalled    ComponentStatus = "installed"
	ComponentStatusInstalling   ComponentStatus = "installing"
	ComponentStatusError        ComponentStatus = "error"
)

type ComponentInfo struct {
	Name    ComponentName   `json:"name"`
	Version string          `json:"version"`
	Status  ComponentStatus `json:"status"`
}

type ComponentManager interface {
	GetInfo(ctx context.Context) ComponentInfo
	Install(ctx context.Context, url string, force bool) error
}
