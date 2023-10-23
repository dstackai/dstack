package executor

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/dstackai/dstack/runner/internal/gerrors"
)

func makeEnv(homeDir string, mappings ...map[string]string) []string {
	list := os.Environ()
	for _, mapping := range mappings {
		for key, value := range mapping {
			list = append(list, fmt.Sprintf("%s=%s", key, value))
		}
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
