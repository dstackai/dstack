package shim

import (
	"context"
	"os"
	"os/exec"
	"strconv"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/docker/docker/api/types/mount"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestDocker_SSHServer pulls ubuntu image (without sshd), installs openssh-server and exits
func TestDocker_SSHServer(t *testing.T) {
	if testing.Short() {
		t.Skip()
	}
	t.Parallel()

	params := &dockerParametersMock{
		commands: []string{"echo 1"},
		sshPort:  nextPort(),
	}

	timeout := 60 // seconds
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeout)*time.Second)
	defer cancel()

	assert.NoError(t, RunDocker(ctx, params, &apiAdapterMock{}))
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

	params := &dockerParametersMock{
		commands:     []string{"sleep 5"},
		sshPort:      nextPort(),
		publicSSHKey: string(publicBytes),
	}

	timeout := 60 // seconds
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeout)*time.Second)
	defer cancel()

	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		assert.NoError(t, RunDocker(ctx, params, &apiAdapterMock{}))
	}()

	for i := 0; i < timeout; i++ {
		cmd := exec.Command("ssh",
			"-o", "StrictHostKeyChecking=no",
			"-o", "UserKnownHostsFile=/dev/null",
			"-i", tempDir+"/id_rsa",
			"-p", strconv.Itoa(params.sshPort),
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

/* Mocks */

type dockerParametersMock struct {
	commands     []string
	sshPort      int
	publicSSHKey string
}

func (c *dockerParametersMock) DockerImageName() string {
	return "ubuntu"
}

func (c *dockerParametersMock) DockerKeepContainer() bool {
	return false
}

func (c *dockerParametersMock) DockerShellCommands() []string {
	commands := make([]string, 0)
	commands = append(commands, getSSHShellCommands(c.sshPort, c.publicSSHKey)...)
	commands = append(commands, c.commands...)
	return commands
}

func (c *dockerParametersMock) DockerPorts() []int {
	ports := make([]int, 0)
	ports = append(ports, c.sshPort)
	return ports
}

func (c *dockerParametersMock) DockerMounts() ([]mount.Mount, error) {
	return nil, nil
}

type apiAdapterMock struct{}

func (s *apiAdapterMock) GetRegistryAuth() ImagePullConfig {
	return ImagePullConfig{}
}

func (s *apiAdapterMock) SetState(string) {}

/* Utilities */

var portNumber int32 = 10000

func nextPort() int {
	return int(atomic.AddInt32(&portNumber, 1))
}
