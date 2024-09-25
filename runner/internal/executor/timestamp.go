package executor

import (
	"context"
	"sync"
	"time"

	"github.com/dstackai/dstack/runner/internal/log"
)

type MonotonicTimestamp struct {
	initial     time.Time
	initialUnix int64 // seconds
	elapsed     int64 // seconds since initial
	counter     int   // surrogate milliseconds
	overflow    bool
	mu          sync.RWMutex
	getNow      func() time.Time
}

func NewMonotonicTimestamp() *MonotonicTimestamp {
	return newMonotonicTimestamp(time.Now)
}

func newMonotonicTimestamp(getNow func() time.Time) *MonotonicTimestamp {
	// getNow must return time.Time with monotonic reading
	now := getNow()
	return &MonotonicTimestamp{
		initial:     now,
		initialUnix: now.Unix(),
		mu:          sync.RWMutex{},
		getNow:      getNow,
	}
}

func (t *MonotonicTimestamp) GetLatest() int64 {
	t.mu.RLock()
	defer t.mu.RUnlock()
	return (t.initialUnix+t.elapsed)*1000 + int64(t.counter)
}

func (t *MonotonicTimestamp) Next() int64 {
	t.mu.Lock()
	now := t.getNow()
	elapsed := int64(now.Sub(t.initial) / time.Second)
	if elapsed == t.elapsed {
		if t.counter < 999 {
			t.counter++
		} else if !t.overflow {
			// warn only once per second to avoid log spamming
			log.Warning(context.TODO(), "Monotonic timestamp counter overflowed", "unix", t.initialUnix+elapsed)
			t.overflow = true
		}
	} else {
		t.elapsed = elapsed
		t.counter = 0
		t.overflow = false
	}
	t.mu.Unlock()
	return t.GetLatest()
}
