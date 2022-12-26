package ports

import (
	"fmt"
	"strconv"
	"sync"

	"github.com/docker/go-connections/nat"
	"github.com/dstackai/dstack/runner/internal/ports/queue"
	"github.com/google/uuid"
)

type mgr struct {
	mu        sync.Mutex
	startPort int
	endPort   int
	pool      map[string]map[string]*string
	free      *queue.Queue
}

var _ Manager = (*mgr)(nil)

func New(startPort, endPort int) Manager {
	m := &mgr{
		startPort: startPort,
		endPort:   endPort,
		mu:        sync.Mutex{},
	}
	m.Reset()
	return m
}

func (m *mgr) Reset() {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.pool = make(map[string]map[string]*string)
	m.free = queue.New()
	for port := m.startPort; port < m.endPort; port++ {
		m.free.Push(strconv.Itoa(port))
	}
}

func (m *mgr) Register(_ int, ports []string) (string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	taskID := uuid.New().String()
	m.pool[taskID] = make(map[string]*string)
	if m.free.IsEmpty() {
		return "", ErrZeroFreePort
	}
	if m.free.Len() < len(ports) {
		return "", ErrZeroFreePort
	}
	for _, k := range ports {
		if port, ok := m.free.Pop(); ok {
			m.pool[taskID][k] = &port
		}
	}
	return taskID, nil
}

func (m *mgr) Ports(id string) []string {
	m.mu.Lock()
	defer m.mu.Unlock()
	if p, ok := m.pool[id]; ok {
		ports := make([]string, 0)
		for _, v := range p {
			ports = append(ports, *v)
		}
		return ports
	}
	return []string{}
}
func (m *mgr) ExposedPorts(id string) nat.PortSet {
	m.mu.Lock()
	defer m.mu.Unlock()
	resp := make(nat.PortSet)
	if _, ok := m.pool[id]; !ok {
		return resp
	}
	for k := range m.pool[id] {
		resp[nat.Port(fmt.Sprintf("%s/tcp", k))] = struct{}{}
	}
	return resp
}

func (m *mgr) BindPorts(id string) nat.PortMap {
	m.mu.Lock()
	defer m.mu.Unlock()
	resp := make(nat.PortMap)
	if _, ok := m.pool[id]; !ok {
		return resp
	}
	for k, v := range m.pool[id] {
		resp[nat.Port(fmt.Sprintf("%s/tcp", k))] = []nat.PortBinding{
			{
				HostIP:   "0.0.0.0",
				HostPort: *v,
			},
		}
	}
	return resp
}
func (m *mgr) Unregister(id string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if p, ok := m.pool[id]; ok {
		for _, kPort := range p {
			m.free.Push(*kPort)
		}
		delete(m.pool, id)
	}
}

func (m *mgr) PortsRange() string {
	return fmt.Sprintf("%d %d", m.startPort, m.endPort-1)
}
