package ports

import (
	"fmt"
	"strconv"
	"sync"

	"github.com/docker/go-connections/nat"
	"github.com/google/uuid"
	"gitlab.com/dstackai/dstackai-runner/internal/ports/queue"
)

type single struct {
	mu        sync.Mutex
	startPort int
	endPort   int
	pool      map[string][]string
	free      *queue.Queue
}

var _ Manager = (*single)(nil)

func NewSingle(startPort, endPort int) Manager {
	m := &single{
		startPort: startPort,
		endPort:   endPort,
		mu:        sync.Mutex{},
	}
	m.Reset()
	return m
}

func (m *single) Reset() {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.pool = make(map[string][]string)
	m.free = queue.New()
	for port := m.startPort; port < m.endPort; port++ {
		m.free.Push(strconv.Itoa(port))
	}
}

func (m *single) Register(count int, ports []string) (string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	taskID := uuid.New().String()
	total := count + len(ports)
	m.pool[taskID] = make([]string, 0)
	if m.free.IsEmpty() {
		return "", ErrZeroFreePort
	}
	if m.free.Len() < total {
		return "", ErrZeroFreePort
	}
	for i := 0; i < total; i++ {
		if port, ok := m.free.Pop(); ok {
			m.pool[taskID] = append(m.pool[taskID], port)
		}
	}
	return taskID, nil
}

func (m *single) Ports(id string) []string {
	m.mu.Lock()
	defer m.mu.Unlock()
	resp := make([]string, 0)
	if p, ok := m.pool[id]; ok {
		for _, port := range p {
			resp = append(resp, port)
		}
	}
	return resp
}
func (m *single) ExposedPorts(id string) nat.PortSet {
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

func (m *single) BindPorts(id string) nat.PortMap {
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
func (m *single) Unregister(id string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if p, ok := m.pool[id]; ok {
		for _, kPort := range p {
			m.free.Push(kPort)
		}
		delete(m.pool, id)
	}
}

func (m *single) PortsRange() string {
	return fmt.Sprintf("%d %d", m.startPort, m.endPort-1)
}
