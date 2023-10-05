package shim

import (
	"context"
	"github.com/docker/docker/api/types/mount"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"os"
	"os/exec"
	"strconv"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// TestDocker_SSHServer pulls ubuntu image (without sshd), installs openssh-server and exits
func TestDocker_SSHServer(t *testing.T) {
	if testing.Short() {
		t.Skip()
	}
	t.Parallel()

	tempDir := t.TempDir()

	dockerParams := &DockerParameters{
		Runner:      &DummyRunnerConfig{dockerCommands: []string{"echo 1"}},
		ImageName:   "ubuntu",
		OpenSSHPort: nextPort(),
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
	t.Parallel()

	tempDir := t.TempDir()
	require.NoError(t, exec.Command("ssh-keygen", "-t", "rsa", "-b", "2048", "-f", tempDir+"/id_rsa", "-q", "-N", "").Run())
	publicBytes, err := os.ReadFile(tempDir + "/id_rsa.pub")
	require.NoError(t, err)

	dockerParams := &DockerParameters{
		Runner:       &DummyRunnerConfig{dockerCommands: []string{"sleep 5"}},
		ImageName:    "ubuntu",
		OpenSSHPort:  nextPort(),
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

func (c *DummyRunnerConfig) GetDockerMount() (*mount.Mount, error) {
	return nil, nil
}

var portNumber int32 = 10000

func nextPort() int {
	return int(atomic.AddInt32(&portNumber, 1))
}
