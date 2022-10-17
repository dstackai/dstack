package repo

import (
	"context"
	"fmt"
	"os"

	"github.com/dstackai/dstackai/runner/internal/log"
	"github.com/go-git/go-git/v5"
	"github.com/go-git/go-git/v5/plumbing"
	"github.com/go-git/go-git/v5/plumbing/transport/http"
	gitssh "github.com/go-git/go-git/v5/plumbing/transport/ssh"
	"golang.org/x/crypto/ssh"
)

type Manager struct {
	ctx       context.Context
	localPath string
	clo       git.CloneOptions
	cho       git.CheckoutOptions
}

func NewManager(ctx context.Context, url, branch, hash string) *Manager {
	ctx = log.AppendArgsCtx(ctx, "url", url, "branch", branch, "hash", hash)
	m := &Manager{
		ctx: ctx,
		clo: git.CloneOptions{
			URL:               url,
			RecurseSubmodules: git.DefaultSubmoduleRecursionDepth,
			ReferenceName:     plumbing.NewBranchReferenceName(branch),
			SingleBranch:      true,
		},
		cho: git.CheckoutOptions{Hash: plumbing.NewHash(hash)},
	}

	return m
}

func (m *Manager) WithLocalPath(path string) *Manager {
	m.localPath = path
	m.ctx = log.AppendArgsCtx(m.ctx, "path", path)
	return m
}

// todo works with Github, possibly not with others
func (m *Manager) WithTokenAuth(token string) *Manager {
	auth := &http.BasicAuth{
		Username: "anything",
		Password: token,
	}
	m.clo.Auth = auth
	return m
}

func (m *Manager) WithSSHAuth(pem, password string) *Manager {
	keys, err := gitssh.NewPublicKeys("git", []byte(pem), password)
	if err != nil {
		log.Warning(m.ctx, "fail to parse SSH private key", "err", err)
	} else {
		keys.HostKeyCallbackHelper.HostKeyCallback = ssh.InsecureIgnoreHostKey()
		m.clo.Auth = keys
	}
	return m
}

func (m *Manager) Checkout() error {
	log.Info(m.ctx, "git checkout", "auth", fmt.Sprintf("%T", (&m.clo).Auth))
	if _, err := os.Stat(m.localPath); !os.IsNotExist(err) {
		if err = os.RemoveAll(m.localPath); err != nil {
			log.Error(m.ctx, "Failed clear directory")
		}
	}
	ref, err := git.PlainClone(m.localPath, false, &m.clo)
	if err != nil && err != git.ErrRepositoryAlreadyExists {
		return err
	}
	if ref != nil {
		workTree, err := ref.Worktree()
		if err != nil {
			return err
		}
		err = workTree.Checkout(&m.cho)
		if err != nil {
			return err
		}
	} else {
		log.Warning(m.ctx, "git clone ref==nil")
	}

	return nil
}
func (m *Manager) CheckoutBranch(branch string) error {
	log.Info(m.ctx, "git checkout", "auth", fmt.Sprintf("%T", (&m.clo).Auth))
	ref, err := git.PlainClone(m.localPath, false, &m.clo)
	if err != nil && err != git.ErrRepositoryAlreadyExists {
		return err
	}
	if ref != nil {
		workTree, err := ref.Worktree()
		if err != nil {
			return err
		}
		cho := git.CheckoutOptions{Branch: plumbing.NewBranchReferenceName(branch)}
		err = workTree.Checkout(&cho)
		if err != nil {
			return err
		}
	} else {
		log.Warning(m.ctx, "git clone ref==nil")
	}

	return nil
}

func (m *Manager) CheckoutMaster() error {
	clo := git.CloneOptions{
		URL: m.clo.URL,
	}
	log.Info(m.ctx, "git checkout", "auth", fmt.Sprintf("%T", clo.Auth))
	_, err := git.PlainClone(m.localPath, false, &clo)
	if err != nil {
		return err
	}

	return nil
}
func (m *Manager) URL() string {
	return m.clo.URL
}
