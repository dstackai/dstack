package gateway

import (
	"fmt"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

type SSHControl struct {
	keyPath       string
	controlPath   string
	hostname      string
	user          string
	remoteTempDir string
	localTempDir  string
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
		user:         "ubuntu",
		localTempDir: localTempDir,
	}
	err = c.mkTempDir()
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
	stdout, err := cmd.Output()
	return stdout, gerrors.Wrap(err)
}

func (c *SSHControl) mkTempDir() error {
	tempDir, err := c.exec(nil, "mktemp -d /tmp/dstack-XXXXXXXX")
	if err != nil {
		return gerrors.Wrap(err)
	}
	c.remoteTempDir = strings.Trim(string(tempDir), "\n")
	return nil
}

func (c *SSHControl) Publish(localPort, publicPort string) error {
	// running tunnel in background
	_, err := c.exec([]string{
		"-f", "-N",
		"-R", fmt.Sprintf("%s/http.sock:localhost:%s", c.remoteTempDir, localPort),
	}, "")
	if err != nil {
		return gerrors.Wrap(err)
	}
	// \\n will be converted to \n by remote printf
	nginxConf := strings.ReplaceAll(fmt.Sprintf(nginxConfFmt, c.remoteTempDir, c.hostname, publicPort), "\n", "\\n")
	script := []string{
		fmt.Sprintf("sudo chown -R %s:www-data %s", c.user, c.remoteTempDir),
		fmt.Sprintf("chmod 0770 %s", c.remoteTempDir),
		fmt.Sprintf("chmod 0660 %s/http.sock", c.remoteTempDir),
		// todo check if conflicts
		fmt.Sprintf("printf '%s' | sudo tee /etc/nginx/sites-enabled/%s-%s.conf", nginxConf, publicPort, c.hostname),
		fmt.Sprintf("sudo systemctl reload nginx.service"),
	}
	_, err = c.exec(nil, strings.Join(script, " && "))
	return gerrors.Wrap(err)
}

func (c *SSHControl) Cleanup() {
	// todo cleanup remote
	// todo kill ssh control
	_ = os.RemoveAll(c.localTempDir)
}

var nginxConfFmt = `upstream tunnel {
  server unix:%s/http.sock;
}

server {
  server_name %s;
  listen      %s;
  
  location / {
    proxy_pass       http://tunnel;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header Host      $host;
  }
}
`
