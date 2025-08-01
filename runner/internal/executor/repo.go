package executor

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"github.com/codeclysm/extract/v4"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/repo"
)

// setupRepo must be called from Run
func (ex *RunExecutor) setupRepo(ctx context.Context) error {
	shouldCheckout, err := ex.shouldCheckout(ctx)
	if err != nil {
		return gerrors.Wrap(err)
	}
	if !shouldCheckout {
		log.Info(ctx, "skipping repo checkout: repo dir is not empty")
		return nil
	}
	// Move existing repo files from the repo dir and back to be able to git clone.
	// Currently, only needed for volumes mounted inside repo with lost+found present.
	tmpRepoDir, err := os.MkdirTemp(ex.tempDir, "repo_dir_copy")
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = os.RemoveAll(tmpRepoDir) }()
	err = ex.moveRepoDir(tmpRepoDir)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() {
		err_ := ex.restoreRepoDir(tmpRepoDir)
		if err == nil {
			err = gerrors.Wrap(err_)
		}
	}()
	switch ex.getRepoData().RepoType {
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
		return gerrors.Newf("unknown RepoType: %s", ex.getRepoData().RepoType)
	}
	return err
}

func (ex *RunExecutor) prepareGit(ctx context.Context) error {
	repoManager := repo.NewManager(
		ctx,
		ex.repoCredentials.CloneURL,
		ex.getRepoData().RepoBranch,
		ex.getRepoData().RepoHash,
		ex.jobSpec.SingleBranch,
	).WithLocalPath(ex.workingDir)
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
	if err := repoManager.SetConfig(ex.getRepoData().RepoConfigName, ex.getRepoData().RepoConfigEmail); err != nil {
		return gerrors.Wrap(err)
	}

	log.Trace(ctx, "Applying diff")
	repoDiff, err := os.ReadFile(ex.codePath)
	if err != nil {
		return gerrors.Wrap(err)
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

func (ex *RunExecutor) shouldCheckout(ctx context.Context) (bool, error) {
	log.Trace(ctx, "checking if repo checkout is needed")
	info, err := os.Stat(ex.workingDir)
	if err != nil {
		if os.IsNotExist(err) {
			if err = os.MkdirAll(ex.workingDir, 0o777); err != nil {
				return false, gerrors.Wrap(err)
			}
			// No repo dir - created a new one
			return true, nil
		}
		return false, gerrors.Wrap(err)
	}
	if !info.IsDir() {
		return false, fmt.Errorf("failed to set up repo dir: %s is not a dir", ex.workingDir)
	}
	entries, err := os.ReadDir(ex.workingDir)
	if err != nil {
		return false, gerrors.Wrap(err)
	}
	if len(entries) == 0 {
		// Repo dir existed but was empty, e.g. a volume without repo
		return true, nil
	}
	if len(entries) > 1 {
		// Repo already checked out, e.g. a volume with repo
		return false, nil
	}
	if entries[0].Name() == "lost+found" {
		// lost+found may be present on a newly created volume
		return true, nil
	}
	return false, nil
}

func (ex *RunExecutor) moveRepoDir(tmpDir string) error {
	if err := moveDir(ex.workingDir, tmpDir); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (ex *RunExecutor) restoreRepoDir(tmpDir string) error {
	if err := moveDir(tmpDir, ex.workingDir); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func moveDir(srcDir, dstDir string) error {
	// We cannot just move/rename files because with volumes they'll be on different devices
	cmd := exec.Command("cp", "-a", srcDir+"/.", dstDir)
	if output, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("failed to cp: %w, output: %s", err, string(output))
	}
	entries, err := os.ReadDir(srcDir)
	if err != nil {
		return gerrors.Wrap(err)
	}
	for _, entry := range entries {
		err := os.RemoveAll(filepath.Join(srcDir, entry.Name()))
		if err != nil {
			return gerrors.Wrap(err)
		}
	}
	return nil
}
