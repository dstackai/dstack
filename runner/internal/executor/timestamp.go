package executor

import (
	"context"
	"github.com/dstackai/dstack/runner/internal/log"
	"sync"
	"time"
)

type MonotonicTimestamp struct {
	unix    int64
	counter int
	mu      sync.RWMutex
}

func NewMonotonicTimestamp() *MonotonicTimestamp {
	return &MonotonicTimestamp{
		unix:    time.Now().Unix(),
		counter: 0,
		mu:      sync.RWMutex{},
	}
}

func (t *MonotonicTimestamp) GetLatest() int64 {
	t.mu.RLock()
	defer t.mu.RUnlock()
	return t.unix*1000 + int64(t.counter)
}

func (t *MonotonicTimestamp) Next() int64 {
	// warning: time.Now() is not monotonic in general
	t.mu.Lock()
	now := time.Now().Unix()
	if now == t.unix {
		t.counter++
		if t.counter == 1000 {
			log.Warning(context.TODO(), "Monotonic timestamp counter overflowed", "timestamp", now)
		}
	} else {
		t.unix = now
		t.counter = 0
	}
	t.mu.Unlock()
	return t.GetLatest()
}
