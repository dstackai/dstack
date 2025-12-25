package ssh

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path"
	"syscall"
	"time"

	"github.com/dstackai/dstack/runner/internal/common"
	"github.com/dstackai/dstack/runner/internal/log"
)

var hostKeys = [...]string{
	"ssh_host_rsa_key",
	"ssh_host_ecdsa_key",
	"ssh_host_ed25519_key",
}

type Sshd struct {
	binPath  string
	confPath string
	logPath  string

	cmd *exec.Cmd
}

func NewSshd(binPath string) *Sshd {
	return &Sshd{
		binPath: binPath,
	}
}

func (d *Sshd) Prepare(ctx context.Context, confDir string, logDir string, port int) error {
	if err := os.MkdirAll(confDir, 0o755); err != nil {
		return fmt.Errorf("create conf dir: %w", err)
	}
	if err := generateHostKeys(ctx, confDir); err != nil {
		return fmt.Errorf("generate host keys: %w", err)
	}
	confPath, err := createSshdConfig(ctx, confDir, port)
	if err != nil {
		return fmt.Errorf("create sshd config: %w", err)
	}
	d.confPath = confPath

	logPath, err := prepareLogPath(logDir)
	if err != nil {
		return fmt.Errorf("prepare log path: %w", err)
	}
	d.logPath = logPath

	// /var/empty is the default path if not configured via ./configure --with-privsep-path=...
	// /run/sshd is used in Debian-based distros, including Ubuntu:
	// https://salsa.debian.org/ssh-team/openssh/-/blob/debian/1%259.7p1-7/debian/rules#L60
	// TODO: change to a custom path if a custom OpenSSH build with overridden PRIVSEP_PATH is used
	if err := preparePrivsepPath("/var/empty"); err != nil {
		return fmt.Errorf("prepare PRIVSEP_PATH: %w", err)
	}
	if err := preparePrivsepPath("/run/sshd"); err != nil {
		return fmt.Errorf("prepare PRIVSEP_PATH: %w", err)
	}

	return nil
}

func (d *Sshd) Start(ctx context.Context) error {
	if d.confPath == "" {
		return errors.New("not configured")
	}
	cmd := exec.CommandContext(ctx, d.binPath, "-D", "-f", d.confPath, "-E", d.logPath)
	cmd.Cancel = func() error {
		return d.sendSigterm()
	}
	cmd.WaitDelay = time.Second * 10
	d.cmd = cmd
	return cmd.Start()
}

func (d *Sshd) Stop(ctx context.Context) error {
	if d.cmd == nil {
		return errors.New("not started")
	}
	if err := d.sendSigterm(); err != nil {
		return err
	}
	return d.cmd.Wait()
}

func (d *Sshd) sendSigterm() error {
	return d.cmd.Process.Signal(syscall.SIGTERM)
}

func generateHostKeys(ctx context.Context, confDir string) error {
	tmpDir, err := os.MkdirTemp("", "dstack-sshd-*")
	if err != nil {
		return err
	}
	defer func() {
		if err := os.RemoveAll(tmpDir); err != nil {
			log.Error(ctx, "Remove host keys temp dir", "err", err)
		}
	}()

	// TODO: change if a custom OpenSSH build with overridden SSHDIR is used
	keyDir := path.Join(tmpDir, "etc/ssh")
	if err := os.MkdirAll(keyDir, 0o700); err != nil {
		return err
	}

	// TODO: specify the full path if a custom OpenSSH build is used
	cmd := exec.CommandContext(ctx, "ssh-keygen", "-A", "-f", tmpDir)
	if err := cmd.Run(); err != nil {
		return err
	}

	for _, key := range hostKeys {
		if err := copyHostKey(keyDir, confDir, key); err != nil {
			return err
		}
	}

	return nil
}

func copyHostKey(srcDir string, destDir string, key string) error {
	srcPath := path.Join(srcDir, key)
	destPath := path.Join(destDir, key)
	privKey, err := os.ReadFile(srcPath)
	if err != nil {
		return err
	}
	if err := os.WriteFile(destPath, privKey, 0o600); err != nil {
		return err
	}

	pubKey, err := os.ReadFile(srcPath + ".pub")
	if err != nil {
		return err
	}
	if err := os.WriteFile(destPath+".pub", pubKey, 0o644); err != nil {
		return err
	}

	return nil
}

func createSshdConfig(ctx context.Context, confDir string, port int) (string, error) {
	confPath := path.Join(confDir, "sshd_config")
	file, err := os.OpenFile(confPath, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0o644)
	if err != nil {
		return "", err
	}
	defer func() {
		if err := file.Close(); err != nil {
			log.Error(ctx, "Close sshd config", "err", err)
		}
	}()

	lines := []string{
		fmt.Sprintf("Port %d", port),
		"PidFile none",
		"Subsystem sftp internal-sftp",
		"PasswordAuthentication no",
		"KbdInteractiveAuthentication no",
		// The default is `no`, but in this case sshd does not allow the user without password to log in,
		// as useradd creates a locked user (with a `!` in the second field of /etc/shadow entry) if no password provided,
		// that is, you cannot log in as `ubuntu` in Ubuntu images or `dstack` in dstack images.
		// See: https://github.com/openssh/openssh-portable/blob/d01efaa1c9ed84fd9011201dbc3c7cb0a82bcee3/auth.c#L108,
		// See: https://github.com/openssh/openssh-portable/blob/master/platform.c#L192-L199
		// See: https://github.com/openssh/openssh-portable/blob/d01efaa1c9ed84fd9011201dbc3c7cb0a82bcee3/configure.ac#L949
		// See: shadow(5)
		// See: useradd(8)
		// TODO: Change to `no` if a custom OpenSSH build without LOCKED_PASSWD_PREFIX is used
		"UsePAM yes",
		"AuthorizedKeysFile .ssh/authorized_keys",
		"AcceptEnv LANG LC_* COLORTERM NO_COLOR",
		"ClientAliveInterval 30",
		"ClientAliveCountMax 4",
	}
	for _, hostKey := range hostKeys {
		lines = append(lines, fmt.Sprintf("HostKey %s/%s", confDir, hostKey))
	}
	for _, line := range lines {
		if _, err := fmt.Fprintln(file, line); err != nil {
			return "", err
		}
	}

	return confPath, nil
}

func prepareLogPath(logDir string) (string, error) {
	if err := os.MkdirAll(logDir, 0o755); err != nil {
		return "", err
	}
	logPath := path.Join(logDir, "sshd.log")
	if _, err := common.RemoveIfExists(logPath); err != nil {
		return "", err
	}
	return logPath, nil
}

func preparePrivsepPath(privsepPath string) error {
	// Ensure that PRIVSEP_PATH 1) exists 2) empty 3) owned by root,
	// see https://github.com/dstackai/dstack/issues/1999
	if err := os.RemoveAll(privsepPath); err != nil {
		return err
	}
	return os.MkdirAll(privsepPath, 0o755)
}
