package executor

import (
	"errors"
	"math"
	"sync"
	"time"

	"github.com/dstackai/dstack/runner/internal/runner/schemas"
)

var ErrLogQuotaExceeded = errors.New("log quota exceeded")

type appendWriter struct {
	mu        *sync.RWMutex // shares with executor
	history   []schemas.LogEvent
	timestamp *MonotonicTimestamp // shares with executor

	quota         int           // bytes per hour, 0 = unlimited
	bytesInHour   int           // bytes written in current hour bucket
	currentHour   int           // monotonic hour bucket index since timeStarted
	timeStarted   time.Time     // monotonic reference point for hour buckets
	quotaExceeded chan struct{} // closed when quota is exceeded (out-of-band signal)
	exceededOnce  sync.Once
}

func newAppendWriter(mu *sync.RWMutex, timestamp *MonotonicTimestamp) *appendWriter {
	return &appendWriter{
		mu:            mu,
		history:       make([]schemas.LogEvent, 0),
		timestamp:     timestamp,
		quotaExceeded: make(chan struct{}),
	}
}

func (w *appendWriter) SetQuota(quota int) {
	w.quota = quota
	w.timeStarted = time.Now()
}

// QuotaExceeded returns a channel that is closed when the log quota is exceeded.
func (w *appendWriter) QuotaExceeded() <-chan struct{} {
	return w.quotaExceeded
}

func (w *appendWriter) Write(p []byte) (n int, err error) {
	w.mu.Lock()
	defer w.mu.Unlock()

	if w.quota > 0 {
		hour := int(math.Floor(time.Since(w.timeStarted).Hours()))
		if hour != w.currentHour {
			w.bytesInHour = 0
			w.currentHour = hour
		}
		if w.bytesInHour+len(p) > w.quota {
			w.exceededOnce.Do(func() { close(w.quotaExceeded) })
			return 0, ErrLogQuotaExceeded
		}
		w.bytesInHour += len(p)
	}

	pCopy := make([]byte, len(p))
	copy(pCopy, p)
	w.history = append(w.history, schemas.LogEvent{Message: pCopy, Timestamp: w.timestamp.Next()})

	return len(p), nil
}
