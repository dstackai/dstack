package executor

import (
	"path/filepath"
	"strings"

	"github.com/dstackai/dstack/runner/internal/gerrors"
)

func joinRelPath(rootDir string, path string) (string, error) {
	if filepath.IsAbs(path) {
		return "", gerrors.New("path must be relative")
	}
	targetPath := filepath.Join(rootDir, path)
	if !strings.HasPrefix(targetPath, rootDir) {
		return "", gerrors.New("path is outside of the root directory")
	}
	return targetPath, nil
}
