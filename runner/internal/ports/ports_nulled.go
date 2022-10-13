package ports

import (
	"github.com/docker/go-connections/nat"
)

var _ Manager = (*mgrNulled)(nil)

type mgrNulled struct{}

func NewNulled() Manager {
	m := new(mgrNulled)
	return m
}

func (m *mgrNulled) Reset() {
}

func (m *mgrNulled) Register(_ int, _ []string) (string, error) {
	return "nulled", nil
}

func (m *mgrNulled) Ports(_ string) []string {
	return nil
}

func (m *mgrNulled) Unregister(_ string) {
}
func (m *mgrNulled) BindPorts(_ string) nat.PortMap {
	return make(nat.PortMap)
}

func (m *mgrNulled) ExposedPorts(_ string) nat.PortSet {
	return make(nat.PortSet)
}
func (m *mgrNulled) PortsRange() string {
	return ""
}
