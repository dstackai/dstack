package executor

import (
	"context"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"

	"github.com/codeclysm/extract/v4"

	"github.com/dstackai/dstack/runner/internal/common"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/repo"
	"github.com/dstackai/dstack/runner/internal/schemas"
)

// setupRepo must be called from Run
// Must be called after setJobWorkingDir and setJobCredentials
func (ex *RunExecutor) setupRepo(ctx context.Context) error {
	log.Trace(ctx, "Setting up repo")
	if ex.jobWorkingDir == "" {
		return errors.New("setup repo: working dir is not set")
	}
	if !filepath.IsAbs(ex.jobWorkingDir) {
		return fmt.Errorf("setup repo: working dir must be absolute: %s", ex.jobWorkingDir)
	}
	if ex.jobSpec.RepoDir == nil {
		return errors.New("repo_dir is not set")
	}

	var err error
	ex.repoDir, err = common.ExpandPath(*ex.jobSpec.RepoDir, ex.jobWorkingDir, ex.jobHomeDir)
	if err != nil {
		return fmt.Errorf("expand repo dir path: %w", err)
	}
	log.Trace(ctx, "Job repo dir", "path", ex.repoDir)

	repoDirIsEmpty, repoDirMustBeMoved, err := ex.checkRepoDir(ctx)
	if err != nil {
		return fmt.Errorf("prepare repo dir: %w", err)
	}
	if !repoDirIsEmpty {
		var repoExistsAction schemas.RepoExistsAction
		if ex.jobSpec.RepoExistsAction != nil {
			repoExistsAction = *ex.jobSpec.RepoExistsAction
		} else {
			log.Debug(ctx, "repo_exists_action is not set, using legacy 'skip' action")
			repoExistsAction = schemas.RepoExistsActionSkip
		}
		switch repoExistsAction {
		case schemas.RepoExistsActionError:
			return fmt.Errorf("setup repo: repo dir is not empty: %s", ex.repoDir)
		case schemas.RepoExistsActionSkip:
			log.Info(ctx, "Skipping repo checkout: repo dir is not empty", "path", ex.repoDir)
			return nil
		default:
			return fmt.Errorf("setup repo: unsupported action: %s", repoExistsAction)
		}
	}

	if repoDirMustBeMoved {
		// Move existing repo files from the repo dir and back to be able to git clone.
		// Currently, only needed for volumes mounted inside repo with lost+found present.
		tmpRepoDir, err := os.MkdirTemp(ex.tempDir, "repo_dir_copy")
		if err != nil {
			return fmt.Errorf("create temp repo dir: %w", err)
		}
		defer func() { _ = os.RemoveAll(tmpRepoDir) }()
		err = ex.moveRepoDir(ctx, tmpRepoDir)
		if err != nil {
			return fmt.Errorf("move repo dir: %w", err)
		}
		defer func() {
			err_ := ex.restoreRepoDir(ctx, tmpRepoDir)
			if err == nil {
				err = fmt.Errorf("restore repo dir: %w", err_)
			}
		}()
	}

	switch ex.getRepoData().RepoType {
	case "remote":
		log.Trace(ctx, "Fetching git repository")
		if err := ex.prepareGit(ctx); err != nil {
			return fmt.Errorf("prepare git repo: %w", err)
		}
	case "local", "virtual":
		log.Trace(ctx, "Extracting tar archive")
		if err := ex.prepareArchive(ctx); err != nil {
			return fmt.Errorf("prepare archive: %w", err)
		}
	default:
		return fmt.Errorf("unknown RepoType: %s", ex.getRepoData().RepoType)
	}

	if err := ex.chownRepoDir(ctx); err != nil {
		return fmt.Errorf("chown repo dir: %w", err)
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
	).WithLocalPath(ex.repoDir)
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
				return fmt.Errorf("private key is empty")
			}
			repoManager.WithSSHAuth(*ex.repoCredentials.PrivateKey, "") // we don't support passphrase
		default:
			return fmt.Errorf("unsupported remote repo protocol: %s", ex.repoCredentials.GetProtocol())
		}
	} else {
		log.Trace(ctx, "Credentials is empty")
	}

	log.Trace(ctx, "Checking out remote repo", "GIT URL", repoManager.URL())
	if err := repoManager.Checkout(ctx); err != nil {
		return fmt.Errorf("checkout repo: %w", err)
	}
	if err := repoManager.SetConfig(ex.getRepoData().RepoConfigName, ex.getRepoData().RepoConfigEmail); err != nil {
		return fmt.Errorf("set repo config: %w", err)
	}

	log.Trace(ctx, "Applying diff")
	repoDiff, err := os.ReadFile(ex.codePath)
	if err != nil {
		return fmt.Errorf("read repo diff: %w", err)
	}
	if len(repoDiff) > 0 {
		if err := repo.ApplyDiff(ctx, ex.repoDir, string(repoDiff)); err != nil {
			return fmt.Errorf("apply diff: %w", err)
		}
	}
	return nil
}

func (ex *RunExecutor) prepareArchive(ctx context.Context) error {
	file, err := os.Open(ex.codePath)
	if err != nil {
		return fmt.Errorf("open code archive: %w", err)
	}
	defer func() { _ = file.Close() }()
	log.Trace(ctx, "Extracting code archive", "src", ex.codePath, "dst", ex.repoDir)
	if err := extract.Tar(ctx, file, ex.repoDir, nil); err != nil {
		return fmt.Errorf("extract tar archive: %w", err)
	}
	return nil
}

func (ex *RunExecutor) checkRepoDir(ctx context.Context) (isEmpty bool, mustBeMoved bool, err error) {
	log.Trace(ctx, "Checking repo dir")
	info, err := os.Stat(ex.repoDir)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			// No repo dir
			return true, false, nil
		}
		return false, false, fmt.Errorf("stat repo dir: %w", err)
	}
	if !info.IsDir() {
		return false, false, fmt.Errorf("stat repo dir: %s is not a dir", ex.repoDir)
	}
	entries, err := os.ReadDir(ex.repoDir)
	if err != nil {
		return false, false, fmt.Errorf("read repo dir: %w", err)
	}
	if len(entries) == 0 {
		// Repo dir is empty
		return true, false, nil
	}
	if len(entries) == 1 && entries[0].Name() == "lost+found" {
		// lost+found may be present on a newly created volume
		// We (but not Git, thus mustBeMoved = true) consider such a dir "empty"
		return true, true, nil
	}
	// Repo dir is not empty
	return false, false, nil
}

func (ex *RunExecutor) moveRepoDir(ctx context.Context, tmpDir string) error {
	if err := moveDir(ctx, ex.repoDir, tmpDir); err != nil {
		return fmt.Errorf("move directory: %w", err)
	}
	return nil
}

func (ex *RunExecutor) restoreRepoDir(ctx context.Context, tmpDir string) error {
	if err := moveDir(ctx, tmpDir, ex.repoDir); err != nil {
		return fmt.Errorf("move directory: %w", err)
	}
	return nil
}

func (ex *RunExecutor) chownRepoDir(ctx context.Context) error {
	log.Trace(ctx, "Chowning repo dir")
	if ex.jobUid == -1 && ex.jobGid == -1 {
		return nil
	}
	return filepath.WalkDir(
		ex.repoDir,
		func(p string, d fs.DirEntry, err error) error {
			// We consider walk/chown errors non-fatal
			if err != nil {
				log.Debug(ctx, "Error while walking repo dir", "path", p, "err", err)
				return nil
			}
			if err := os.Chown(p, ex.jobUid, ex.jobGid); err != nil {
				log.Debug(ctx, "Error while chowning repo dir", "path", p, "err", err)
			}
			return nil
		},
	)
}

func moveDir(ctx context.Context, srcDir, dstDir string) error {
	// We cannot just move/rename files because with volumes they'll be on different devices
	cmd := exec.CommandContext(ctx, "cp", "-a", srcDir+"/.", dstDir)
	if output, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("failed to cp: %w, output: %s", err, string(output))
	}
	entries, err := os.ReadDir(srcDir)
	if err != nil {
		return fmt.Errorf("read source directory: %w", err)
	}
	for _, entry := range entries {
		err := os.RemoveAll(filepath.Join(srcDir, entry.Name()))
		if err != nil {
			return fmt.Errorf("remove file from source: %w", err)
		}
	}
	return nil
}
