package executor

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestJoinRelPath(t *testing.T) {
	base := "/tmp/repo"
	var err error
	var res string

	res, err = joinRelPath(base, ".")
	assert.NoError(t, err)
	assert.Equal(t, "/tmp/repo", res)

	_, err = joinRelPath(base, "..")
	assert.Error(t, err)

	res, err = joinRelPath(base, "task")
	assert.NoError(t, err)
	assert.Equal(t, "/tmp/repo/task", res)

	_, err = joinRelPath(base, "/tmp/repo/task")
	assert.Error(t, err)
}
