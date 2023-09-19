package executor

import (
	"github.com/stretchr/testify/assert"
	"testing"
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

func TestJoinShellCommand(t *testing.T) {
	var res []string

	res = joinShellCommands([]string{})
	assert.Equal(t, []string{}, res)

	res = joinShellCommands([]string{"echo 1"})
	assert.Equal(t, []string{"echo 1"}, res)

	res = joinShellCommands([]string{"echo 1", "echo 2"})
	assert.Equal(t, []string{"echo 1 && echo 2"}, res)

	res = joinShellCommands([]string{"echo 1", "echo 2 &"})
	assert.Equal(t, []string{"echo 1 && { echo 2 & }"}, res)
}
