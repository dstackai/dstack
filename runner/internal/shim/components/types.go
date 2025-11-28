package components

type ComponentName string

const ComponentNameRunner ComponentName = "dstack-runner"

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
