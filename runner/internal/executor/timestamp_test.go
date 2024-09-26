package executor

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestTimestamp_Counter(t *testing.T) {
	now := time.Now()
	ts := newMonotonicTimestamp(func() time.Time { return now })
	initial := ts.GetLatest()
	assert.Equal(t, int64(1), ts.Next()-initial)
	assert.Equal(t, int64(2), ts.Next()-initial)
	now = now.Add(999 * time.Millisecond)
	assert.Equal(t, int64(3), ts.Next()-initial)
	now = now.Add(100 * time.Millisecond)
	assert.Equal(t, int64(1000), ts.Next()-initial)
	assert.Equal(t, int64(1001), ts.Next()-initial)
}

func TestTimestamp_CounterOverflow(t *testing.T) {
	now := time.Now()
	ts := newMonotonicTimestamp(func() time.Time { return now })
	initial := ts.GetLatest()
	for i := 0; i < 997; i++ {
		ts.Next()
	}
	assert.Equal(t, int64(998), ts.Next()-initial)
	assert.False(t, ts.overflow)
	assert.Equal(t, int64(999), ts.Next()-initial)
	assert.False(t, ts.overflow)
	assert.Equal(t, int64(999), ts.Next()-initial)
	assert.True(t, ts.overflow)
	assert.Equal(t, int64(999), ts.Next()-initial)
	assert.True(t, ts.overflow)
	now = now.Add(time.Second)
	assert.Equal(t, int64(1000), ts.Next()-initial)
	assert.False(t, ts.overflow)
	assert.Equal(t, int64(1001), ts.Next()-initial)
	assert.False(t, ts.overflow)
}
