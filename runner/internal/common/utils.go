package common

import (
	"context"
	"errors"
	"os"
	"path"
	"slices"

	"github.com/dstackai/dstack/runner/internal/log"
)

func PathExists(pth string) (bool, error) {
	_, err := os.Stat(pth)
	if err == nil {
		return true, nil
	}
	if errors.Is(err, os.ErrNotExist) {
		return false, nil
	}
	return false, err
}

func RemoveIfExists(pth string) (bool, error) {
	err := os.Remove(pth)
	if err == nil {
		return true, nil
	}
	if errors.Is(err, os.ErrNotExist) {
		return false, nil
	}
	return false, err
}

func ExpandPath(pth string, base string, home string) (string, error) {
	pth = path.Clean(pth)
	if pth == "~" {
		return path.Clean(home), nil
	}
	if len(pth) >= 2 && pth[0] == '~' {
		if pth[1] == '/' {
			return path.Join(home, pth[2:]), nil
		}
		return "", errors.New("~username syntax is not supported")
	}
	if base != "" && !path.IsAbs(pth) {
		return path.Join(base, pth), nil
	}
	return pth, nil
}

func MkdirAll(ctx context.Context, pth string, uid int, gid int) error {
	paths := []string{pth}
	for {
		pth = path.Dir(pth)
		if pth == "/" || pth == "." {
			break
		}
		paths = append(paths, pth)
	}
	for _, p := range slices.Backward(paths) {
		if _, err := os.Stat(p); errors.Is(err, os.ErrNotExist) {
			if err := os.Mkdir(p, 0o755); err != nil {
				return err
			}
			if uid != -1 || gid != -1 {
				if err := os.Chown(p, uid, gid); err != nil {
					log.Warning(ctx, "Failed to chown", "path", p, "err", err)
				}
			}
		} else if err != nil {
			return err
		}
	}
	return nil
}
