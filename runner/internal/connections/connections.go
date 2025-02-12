package connections

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/prometheus/procfs"
)

const connStateEstablished = 1

type connection struct {
	fromAddr string
	fromPort uint64
}

type trackingInfo struct {
	firstSeenAt time.Time
}

type ConnectionTrackerConfig struct {
	Port            uint64
	MinConnDuration time.Duration
	Procfs          procfs.FS
}

// Tracks TCP connections to a specified port.
type ConnectionTracker struct {
	cfg              ConnectionTrackerConfig
	connections      map[connection]trackingInfo
	lastConnectionAt *time.Time
	lastCheckedAt    *time.Time
	stopChan         chan struct{}
	mu               sync.RWMutex
}

func NewConnectionTracker(cfg ConnectionTrackerConfig) *ConnectionTracker {
	tracker := ConnectionTracker{
		cfg:              cfg,
		connections:      make(map[connection]trackingInfo),
		lastConnectionAt: nil,
		lastCheckedAt:    nil,
		stopChan:         make(chan struct{}),
		mu:               sync.RWMutex{},
	}
	return &tracker
}

// Returns the number of seconds since the last connection was closed or
// since tracking started. If tracking hasn't started yet, returns 0.
func (t *ConnectionTracker) GetNoConnectionsSecs() int64 {
	t.mu.RLock()
	defer t.mu.RUnlock()
	if t.lastConnectionAt == nil || t.lastCheckedAt == nil {
		return 0
	}
	return int64(t.lastCheckedAt.Sub(*t.lastConnectionAt).Seconds())
}

func (t *ConnectionTracker) Track(ticker <-chan time.Time) {
	for {
		select {
		case now := <-ticker:
			t.updateConnections(now)
		case <-t.stopChan:
			return
		}
	}
}

func (t *ConnectionTracker) Stop() {
	t.stopChan <- struct{}{}
}

func (t *ConnectionTracker) updateConnections(now time.Time) {
	currentConnections, err := t.getCurrentConnections()
	if err != nil {
		log.Error(context.TODO(), "Failed to retrieve connections: %v", err)
		return
	}
	t.mu.Lock()
	defer t.mu.Unlock()
	// evict closed connections
	for conn := range t.connections {
		if _, ok := currentConnections[conn]; !ok {
			delete(t.connections, conn)
		}
	}
	// add new connections
	for conn := range currentConnections {
		if _, ok := t.connections[conn]; !ok {
			t.connections[conn] = trackingInfo{firstSeenAt: now}
		}
	}
	// update lastConnectionAt
	for _, connInfo := range t.connections {
		if now.Sub(connInfo.firstSeenAt) > t.cfg.MinConnDuration {
			t.lastConnectionAt = &now
			break
		}
	}
	if t.lastConnectionAt == nil { // first call to updateConnections
		t.lastConnectionAt = &now
	}
	t.lastCheckedAt = &now
}

func (t *ConnectionTracker) getCurrentConnections() (map[connection]struct{}, error) {
	connections := make(map[connection]struct{})
	netTCP, err := t.cfg.Procfs.NetTCP()
	if err != nil {
		return nil, fmt.Errorf("Failed to retrieve IPv4 network connections: %w", err)
	}
	netTCP6, err := t.cfg.Procfs.NetTCP6()
	if err != nil {
		return nil, fmt.Errorf("Failed to retrieve IPv6 network connections: %w", err)
	}
	for _, conn := range append(netTCP, netTCP6...) {
		if conn.LocalPort == t.cfg.Port && conn.St == connStateEstablished {
			connections[connection{
				fromAddr: conn.RemAddr.String(),
				fromPort: conn.RemPort,
			}] = struct{}{}
		}
	}
	return connections, nil
}
