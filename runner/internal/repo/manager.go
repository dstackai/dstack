package repo

import (
	"context"
	"fmt"

	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
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
	hash      string
}

func NewManager(ctx context.Context, url, branch, hash string, singleBranch bool) *Manager {
	ctx = log.AppendArgsCtx(ctx, "url", url, "branch", branch, "hash", hash)
	m := &Manager{
		ctx: ctx,
		clo: git.CloneOptions{
			URL:               url,
			RecurseSubmodules: git.DefaultSubmoduleRecursionDepth,
			ReferenceName:     plumbing.NewBranchReferenceName(branch),
			SingleBranch:      singleBranch,
		},
		hash: hash,
	}

	return m
}

func (m *Manager) WithLocalPath(path string) *Manager {
	m.localPath = path
	m.ctx = log.AppendArgsCtx(m.ctx, "path", path)
	return m
}

// TODO: works with Github, possibly not with others
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
	ref, err := git.PlainClone(m.localPath, false, &m.clo)
	if err != nil {
		return gerrors.Wrap(err)
	}
	if ref != nil {
		branchRef, err := ref.Reference(m.clo.ReferenceName, true)
		if err != nil {
			return gerrors.Wrap(err)
		}
		var cho git.CheckoutOptions
		if m.hash == "" || m.hash == branchRef.Hash().String() {
			cho.Branch = m.clo.ReferenceName
		} else {
			cho.Hash = plumbing.NewHash(m.hash)
		}
		workTree, err := ref.Worktree()
		if err != nil {
			return gerrors.Wrap(err)
		}
		err = workTree.Checkout(&cho)
		if err != nil {
			return gerrors.Wrap(err)
		}
	} else {
		log.Warning(m.ctx, "git clone ref==nil")
	}

	return nil
}

func (m *Manager) URL() string {
	return m.clo.URL
}

func (m *Manager) SetConfig(name, email string) error {
	repo, err := git.PlainOpen(m.localPath)
	if err != nil {
		return gerrors.Wrap(err)
	}
	config, err := repo.Config()
	if err != nil {
		return gerrors.Wrap(err)
	}
	config.User.Name = name
	config.User.Email = email
	if err := repo.SetConfig(config); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}
