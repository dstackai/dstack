package queue

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestQueue(t *testing.T) {
	q := New()
	q.Push("first")
	q.Push("second")
	q.Push("third")
	assert.Equal(t, q.Len(), 3)
	el, ok := q.Pop()
	assert.Equal(t, ok, true)
	assert.Equal(t, el, "first")
	assert.Equal(t, q.Len(), 2)
	q.Push("fourth")
	el, ok = q.Pop()
	assert.Equal(t, ok, true)
	assert.Equal(t, el, "second")
	assert.Equal(t, q.Len(), 2)
	el, ok = q.Pop()
	assert.Equal(t, ok, true)
	assert.Equal(t, el, "third")
	assert.Equal(t, q.Len(), 1)
	el, ok = q.Pop()
	assert.Equal(t, ok, true)
	assert.Equal(t, el, "fourth")
	assert.Equal(t, q.Len(), 0)
	el, ok = q.Pop()
	assert.Equal(t, ok, false)
	assert.Equal(t, el, "")
	assert.Equal(t, q.Len(), 0)
}
