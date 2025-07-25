package shim

import (
	"context"
	"encoding/hex"
	"math/rand"
	"os"
	"os/exec"
	"strconv"
	"strings"
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
		commands:  []string{"echo 1"},
		sshPort:   nextPort(),
		runnerDir: t.TempDir(),
	}

	timeout := 180 // seconds
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeout)*time.Second)
	defer cancel()

	dockerRunner, _ := NewDockerRunner(ctx, params)
	taskConfig := createTaskConfig(t)
	defer dockerRunner.Remove(context.Background(), taskConfig.ID)

	assert.NoError(t, dockerRunner.Submit(ctx, taskConfig))
	assert.NoError(t, dockerRunner.Run(ctx, taskConfig.ID))
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
		runnerDir:    t.TempDir(),
	}

	timeout := 180 // seconds
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeout)*time.Second)
	defer cancel()

	dockerRunner, _ := NewDockerRunner(ctx, params)

	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		taskConfig := createTaskConfig(t)
		defer dockerRunner.Remove(context.Background(), taskConfig.ID)

		assert.NoError(t, dockerRunner.Submit(ctx, taskConfig))
		assert.NoError(t, dockerRunner.Run(ctx, taskConfig.ID))
	}()

	for i := 0; i < timeout; i++ {
		cmd := exec.Command("ssh",
			"-F", "none",
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

func TestDocker_ShmNoexecByDefault(t *testing.T) {
	if testing.Short() {
		t.Skip()
	}
	t.Parallel()

	params := &dockerParametersMock{
		commands:  []string{"mount | grep '/dev/shm .*size=65536k' | grep noexec"},
		runnerDir: t.TempDir(),
	}

	timeout := 180 // seconds
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeout)*time.Second)
	defer cancel()

	dockerRunner, _ := NewDockerRunner(ctx, params)
	taskConfig := createTaskConfig(t)
	defer dockerRunner.Remove(context.Background(), taskConfig.ID)

	assert.NoError(t, dockerRunner.Submit(ctx, taskConfig))
	assert.NoError(t, dockerRunner.Run(ctx, taskConfig.ID))
}

func TestDocker_ShmExecIfSizeSpecified(t *testing.T) {
	if testing.Short() {
		t.Skip()
	}
	t.Parallel()

	params := &dockerParametersMock{
		commands:  []string{"mount | grep '/dev/shm .*size=1024k' | grep -v noexec"},
		runnerDir: t.TempDir(),
	}

	timeout := 180 // seconds
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeout)*time.Second)
	defer cancel()

	dockerRunner, _ := NewDockerRunner(ctx, params)
	taskConfig := createTaskConfig(t)
	taskConfig.ShmSize = 1024 * 1024
	defer dockerRunner.Remove(context.Background(), taskConfig.ID)

	assert.NoError(t, dockerRunner.Submit(ctx, taskConfig))
	assert.NoError(t, dockerRunner.Run(ctx, taskConfig.ID))
}

/* Mocks */

type dockerParametersMock struct {
	// If sshPort is not set (equals zero), sshd won't be started.
	commands     []string
	sshPort      int
	publicSSHKey string
	runnerDir    string
}

func (c *dockerParametersMock) DockerPrivileged() bool {
	return false
}

func (c *dockerParametersMock) DockerPJRTDevice() string {
	return ""
}

func (c *dockerParametersMock) DockerShellCommands(publicKeys []string) []string {
	userPublicKey := c.publicSSHKey
	if len(publicKeys) > 0 {
		userPublicKey = strings.Join(publicKeys, "\n")
	}
	commands := make([]string, 0)
	if c.sshPort != 0 {
		commands = append(commands, getSSHShellCommands(c.sshPort, userPublicKey)...)
	}
	commands = append(commands, c.commands...)
	return commands
}

func (c *dockerParametersMock) DockerPorts() []int {
	ports := make([]int, 0)
	if c.sshPort != 0 {
		ports = append(ports, c.sshPort)
	}
	return ports
}

func (c *dockerParametersMock) DockerMounts(string) ([]mount.Mount, error) {
	return nil, nil
}

func (c *dockerParametersMock) MakeRunnerDir(string) (string, error) {
	return c.runnerDir, nil
}

/* Utilities */

var portNumber int32 = 10000

func nextPort() int {
	return int(atomic.AddInt32(&portNumber, 1))
}

var (
	randSrc = rand.New(rand.NewSource(time.Now().UnixNano()))
	randMu  = sync.Mutex{}
)

func generateID(t *testing.T) string {
	const idLen = 16
	b := make([]byte, idLen/2)
	randMu.Lock()
	defer randMu.Unlock()
	_, err := randSrc.Read(b)
	require.Nil(t, err)
	return hex.EncodeToString(b)[:idLen]
}

func createTaskConfig(t *testing.T) TaskConfig {
	return TaskConfig{
		ID:        generateID(t),
		Name:      t.Name(),
		ImageName: "ubuntu",
	}
}
