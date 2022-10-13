package ports

import "github.com/docker/go-connections/nat"

type Manager interface {
	Reset()
	Register(cnt int, ports []string) (string, error)
	Ports(id string) []string
	Unregister(id string)
	BindPorts(id string) nat.PortMap
	ExposedPorts(id string) nat.PortSet
	PortsRange() string
}
