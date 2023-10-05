package executor

import (
	"fmt"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"path/filepath"
	"strings"
)

func makeEnv(homeDir string, mapping map[string]string, secrets map[string]string) []string {
	// todo set job vars
	list := make([]string, 0)
	for key, value := range mapping {
		list = append(list, fmt.Sprintf("%s=%s", key, value))
	}
	for key, value := range secrets {
		list = append(list, fmt.Sprintf("%s=%s", key, value))
	}
	list = append(list, fmt.Sprintf("HOME=%s", homeDir))
	return list
}

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
