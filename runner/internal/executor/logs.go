package executor

import (
	"sync"

	"github.com/dstackai/dstack/runner/internal/schemas"
)

type appendWriter struct {
	mu        *sync.RWMutex // shares with executor
	history   []schemas.LogEvent
	timestamp *MonotonicTimestamp // shares with executor
}

func newAppendWriter(mu *sync.RWMutex, timestamp *MonotonicTimestamp) *appendWriter {
	return &appendWriter{
		mu:        mu,
		history:   make([]schemas.LogEvent, 0),
		timestamp: timestamp,
	}
}

func (w *appendWriter) Write(p []byte) (n int, err error) {
	w.mu.Lock()
	defer w.mu.Unlock()

	pCopy := make([]byte, len(p))
	copy(pCopy, p)
	w.history = append(w.history, schemas.LogEvent{Message: pCopy, Timestamp: w.timestamp.Next()})

	return len(p), nil
}
