package shim

import (
	"context"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"os"
	"os/exec"
	"strconv"
	"sync"
	"testing"
	"time"
)

// TestDocker_SSHServer pulls ubuntu image (without sshd), installs openssh-server and exits
func TestDocker_SSHServer(t *testing.T) {
	if testing.Short() {
		t.Skip()
	}

	tempDir := t.TempDir()

	dockerParams := &DockerParameters{
		Runner:      &DummyRunnerConfig{dockerCommands: []string{"echo 1"}},
		ImageName:   "ubuntu",
		OpenSSHPort: 10022,
		DstackHome:  tempDir + "/.dstack",
	}

	timeout := 60 // seconds
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeout)*time.Second)
	defer cancel()

	assert.NoError(t, RunDocker(ctx, dockerParams))
}

// TestDocker_SSHServerConnect pulls ubuntu image (without sshd), installs openssh-server and tries to connect via SSH
func TestDocker_SSHServerConnect(t *testing.T) {
	if testing.Short() {
		t.Skip()
	}

	tempDir := t.TempDir()
	require.NoError(t, exec.Command("ssh-keygen", "-t", "rsa", "-b", "2048", "-f", tempDir+"/id_rsa", "-q", "-N", "").Run())
	publicBytes, err := os.ReadFile(tempDir + "/id_rsa.pub")
	require.NoError(t, err)

	dockerParams := &DockerParameters{
		Runner:       &DummyRunnerConfig{dockerCommands: []string{"sleep 5"}},
		ImageName:    "ubuntu",
		OpenSSHPort:  10022,
		PublicSSHKey: string(publicBytes),
		DstackHome:   tempDir + "/.dstack",
	}

	timeout := 60 // seconds
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeout)*time.Second)
	defer cancel()

	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		assert.NoError(t, RunDocker(ctx, dockerParams))
	}()

	for i := 0; i < timeout; i++ {
		cmd := exec.Command("ssh",
			"-o", "StrictHostKeyChecking=no",
			"-o", "UserKnownHostsFile=/dev/null",
			"-i", tempDir+"/id_rsa",
			"-p", strconv.Itoa(dockerParams.OpenSSHPort),
			"root@localhost", "whoami",
		)
		output, err := cmd.Output()
		if err == nil {
			assert.Equal(t, "root\n", string(output))
			break
		}
		time.Sleep(time.Second) // 1 attempt per second
	}
	wg.Wait()
}

type DummyRunnerConfig struct {
	dockerCommands []string
}

func (c *DummyRunnerConfig) GetDockerCommands() []string {
	return c.dockerCommands
}

func (c *DummyRunnerConfig) GetTempDir() string {
	return "/tmp/runner"
}
