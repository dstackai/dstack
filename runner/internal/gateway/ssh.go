package gateway

import (
	"bytes"
	"fmt"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"os"
	"os/exec"
	"path/filepath"
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
	}
	if args != nil {
		allArgs = append(allArgs, args...)
	}
	allArgs = append(allArgs, fmt.Sprintf("%s@%s", c.user, c.hostname))
	if command != "" {
		allArgs = append(allArgs, command)
	}
	fmt.Println(allArgs)
	cmd := exec.Command("ssh", allArgs...)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return nil, gerrors.Newf("ssh exec: %s", stderr.String())
	}
	return stdout.Bytes(), nil
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
