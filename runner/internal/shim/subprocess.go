package shim

import (
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"os"
	"path/filepath"
)

func RunSubprocess(httpPort int, logLevel int, runnerVersion string, useDev bool) error {
	userHomeDir, err := os.UserHomeDir()
	if err != nil {
		return gerrors.Wrap(err)
	}
	runnerPath := filepath.Join(userHomeDir, ".dstack/dstack-runner")
	if err = os.MkdirAll(filepath.Dir(runnerPath), 0755); err != nil {
		return gerrors.Wrap(err)
	}

	err = downloadRunner(runnerVersion, useDev, runnerPath)
	if err != nil {
		return gerrors.Wrap(err)
	}
	// todo create temporary, home and working dirs
	// todo start runner
	// todo wait till runner completes
	return nil
}
