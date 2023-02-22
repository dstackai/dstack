package ports

import (
	"fmt"
	"sync"

	"github.com/docker/go-connections/nat"
	"github.com/google/uuid"
)

type system struct {
	mu   sync.Mutex
	pool map[string][]string
}

var _ Manager = (*system)(nil)

func NewSystem() Manager {
	m := &system{
		mu: sync.Mutex{},
	}
	m.Reset()
	return m
}

func (m *system) Reset() {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.pool = make(map[string][]string)
}

func (m *system) Register(count int, ports []string) (string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	taskID := uuid.New().String()
	total := count + len(ports)
	m.pool[taskID] = make([]string, 0)
	for i := 0; i < total; i++ {
		if port, err := GetFreePort(); err == nil {
			m.pool[taskID] = append(m.pool[taskID], fmt.Sprintf("%d", port))
		}
	}
	return taskID, nil
}

func (m *system) Ports(id string) []string {
	m.mu.Lock()
	defer m.mu.Unlock()
	resp := make([]string, 0)
	if p, ok := m.pool[id]; ok {
		resp = append(resp, p...)
	}
	return resp
}
func (m *system) ExposedPorts(id string) nat.PortSet {
	m.mu.Lock()
	defer m.mu.Unlock()
	resp := make(nat.PortSet)
	if _, ok := m.pool[id]; !ok {
		return resp
	}
	for _, port := range m.pool[id] {
		resp[nat.Port(fmt.Sprintf("%s/tcp", port))] = struct{}{}
	}
	return resp
}

func (m *system) BindPorts(id string) nat.PortMap {
	m.mu.Lock()
	defer m.mu.Unlock()
	resp := make(nat.PortMap)
	if _, ok := m.pool[id]; !ok {
		return resp
	}
	for _, port := range m.pool[id] {
		resp[nat.Port(fmt.Sprintf("%s/tcp", port))] = []nat.PortBinding{
			{
				HostIP:   "0.0.0.0",
				HostPort: port,
			},
		}
	}
	return resp
}
func (m *system) Unregister(id string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	delete(m.pool, id)
}

func (m *system) PortsRange() string {
	return "0 0"
}
