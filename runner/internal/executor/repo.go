package executor

import (
	"context"
	"os"

	"github.com/codeclysm/extract/v3"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/repo"
)

// setupRepo must be called from Run
func (ex *RunExecutor) setupRepo(ctx context.Context) error {
	if _, err := os.Stat(ex.workingDir); err != nil {
		if err = os.MkdirAll(ex.workingDir, 0o777); err != nil {
			return gerrors.Wrap(err)
		}
	}
	switch ex.run.RepoData.RepoType {
	case "remote":
		log.Trace(ctx, "Fetching git repository")
		if err := ex.prepareGit(ctx); err != nil {
			return gerrors.Wrap(err)
		}
	case "local", "virtual":
		log.Trace(ctx, "Extracting tar archive")
		if err := ex.prepareArchive(ctx); err != nil {
			return gerrors.Wrap(err)
		}
	default:
		return gerrors.Newf("unknown RepoType: %s", ex.run.RepoData.RepoType)
	}
	return nil
}

func (ex *RunExecutor) prepareGit(ctx context.Context) error {
	repoManager := repo.NewManager(ctx, ex.repoCredentials.CloneURL, ex.run.RepoData.RepoBranch, ex.run.RepoData.RepoHash).WithLocalPath(ex.workingDir)
	if ex.repoCredentials != nil {
		log.Trace(ctx, "Credentials is not empty")
		switch ex.repoCredentials.GetProtocol() {
		case "https":
			log.Trace(ctx, "Select HTTPS protocol")
			if ex.repoCredentials.OAuthToken == nil {
				log.Warning(ctx, "OAuth token is empty")
				break
			}
			repoManager.WithTokenAuth(*ex.repoCredentials.OAuthToken)
		case "ssh":
			log.Trace(ctx, "Select SSH protocol")
			if ex.repoCredentials.PrivateKey == nil {
				return gerrors.Newf("private key is empty")
			}
			repoManager = repo.NewManager(ctx, ex.repoCredentials.CloneURL, ex.run.RepoData.RepoBranch, ex.run.RepoData.RepoHash).WithLocalPath(ex.workingDir)
			repoManager.WithSSHAuth(*ex.repoCredentials.PrivateKey, "") // we don't support passphrase
		default:
			return gerrors.Newf("unsupported remote repo protocol: %s", ex.repoCredentials.GetProtocol())
		}
	} else {
		log.Trace(ctx, "Credentials is empty")
	}

	log.Trace(ctx, "Checking out remote repo", "GIT URL", repoManager.URL())
	if err := repoManager.Checkout(); err != nil {
		return gerrors.Wrap(err)
	}
	if err := repoManager.SetConfig(ex.run.RepoData.RepoConfigName, ex.run.RepoData.RepoConfigEmail); err != nil {
		return gerrors.Wrap(err)
	}

	log.Trace(ctx, "Applying diff")
	repoDiff, err := os.ReadFile(ex.codePath)
	if err != nil {
		return err
	}
	if len(repoDiff) > 0 {
		if err := repo.ApplyDiff(ctx, ex.workingDir, string(repoDiff)); err != nil {
			return gerrors.Wrap(err)
		}
	}
	return nil
}

func (ex *RunExecutor) prepareArchive(ctx context.Context) error {
	file, err := os.Open(ex.codePath)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = file.Close() }()
	log.Trace(ctx, "Extracting code archive", "src", ex.codePath, "dst", ex.workingDir)
	if err := extract.Tar(ctx, file, ex.workingDir, nil); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}
