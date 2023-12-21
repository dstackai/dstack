package gateway

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"github.com/dstackai/dstack/runner/internal/gerrors"
)

type SSHControl struct {
	keyPath      string
	controlPath  string
	hostname     string
	user         string
	localTempDir string
}

func NewSSHControl(hostname, sshKey string) (*SSHControl, error) {
	localTempDir, err := os.MkdirTemp("", "")
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	keyPath := filepath.Join(localTempDir, "id_rsa")
	if err := os.WriteFile(keyPath, []byte(sshKey), 0o600); err != nil {
		return nil, gerrors.Wrap(err)
	}
	c := &SSHControl{
		keyPath:      keyPath,
		controlPath:  filepath.Join(localTempDir, "ssh.control"),
		hostname:     hostname,
		user:         "www-data",
		localTempDir: localTempDir,
	}
	return c, gerrors.Wrap(err)
}

func (c *SSHControl) exec(args []string, command string) ([]byte, error) {
	allArgs := []string{
		"-i", c.keyPath,
		"-o", "StrictHostKeyChecking=accept-new",
		"-o", fmt.Sprintf("ControlPath=%s", c.controlPath),
		"-o", "ControlMaster=auto",
		"-o", "ControlPersist=yes",
		"-o", "ServerAliveInterval=60",
	}
	if args != nil {
		allArgs = append(allArgs, args...)
	}
	allArgs = append(allArgs, fmt.Sprintf("%s@%s", c.user, c.hostname))
	if command != "" {
		allArgs = append(allArgs, command)
	}
	cmd := exec.Command("ssh", allArgs...)

	stdoutFile, err := os.CreateTemp("", "")
	if err != nil {
		panic(err)
	}
	defer func() { _ = os.Remove(stdoutFile.Name()) }()
	stderrFile, err := os.CreateTemp("", "")
	if err != nil {
		panic(err)
	}
	defer func() { _ = os.Remove(stderrFile.Name()) }()
	// OpenSSH 8.2 (on Ubuntu 20.04) doesn't close stdout/stderr when running in the background (-f option).
	// Run command waits indefinitely for closing pipes, but exits immediately if we are using files.
	cmd.Stdout = stdoutFile
	cmd.Stderr = stderrFile

	if err := cmd.Run(); err != nil {
		stderr, _ := os.ReadFile(stderrFile.Name())
		return nil, gerrors.Newf("ssh exec: %s", string(stderr))
	}
	stdout, _ := os.ReadFile(stdoutFile.Name())
	return stdout, nil
}

func (c *SSHControl) Publish(localPort, sockPath string) error {
	_, err := c.exec([]string{
		"-f", "-N",
		"-R", fmt.Sprintf("%s:localhost:%s", sockPath, localPort),
	}, "")
	return gerrors.Wrap(err)
}

func (c *SSHControl) Cleanup() {
	// todo cleanup remote
	_ = exec.Command("ssh", "-o", "ControlPath="+c.controlPath, "-O", "exit", c.hostname).Run()
	_ = os.RemoveAll(c.localTempDir)
}
