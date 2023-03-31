package container

import (
	"github.com/stretchr/testify/assert"
	"testing"
)

func TestShellCommandsEmpty(t *testing.T) {
	cmd := ShellCommands([]string{})
	assert.Equal(t, 0, len(cmd))
}

func TestShellCommandsSingle(t *testing.T) {
	cmd := "echo 123"
	args := ShellCommands([]string{cmd})[0]
	assert.Equal(t, cmd, args)
}

func TestShellCommandsAnd(t *testing.T) {
	args := ShellCommands([]string{"echo 123", "whoami"})[0]
	assert.Equal(t, "echo 123 && whoami", args)
}

func TestShellCommandsBackground(t *testing.T) {
	args := ShellCommands([]string{"sleep 5 &", "echo 123"})[0]
	assert.Equal(t, "{ sleep 5 & } && echo 123", args)
}

func TestShellCommandsBackgroundSpaced(t *testing.T) {
	args := ShellCommands([]string{"sleep 5 & ", "echo 123"})[0]
	assert.Equal(t, "{ sleep 5 & } && echo 123", args)
}
