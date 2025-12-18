package components

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/dstackai/dstack/runner/internal/common"
	"github.com/dstackai/dstack/runner/internal/log"
)

const downloadTimeout = 10 * time.Minute

func downloadFile(ctx context.Context, url string, path string, mode os.FileMode, force bool) error {
	if _, err := os.Stat(path); err == nil {
		if force {
			log.Debug(ctx, "file exists, forcing download", "path", path)
		} else {
			log.Debug(ctx, "file exists, skipping download", "path", path)
			return nil
		}
	} else if !os.IsNotExist(err) {
		return fmt.Errorf("check file exists: %w", err)
	}
	dir, name := filepath.Split(path)
	tempFile, err := os.CreateTemp(dir, fmt.Sprintf(".*-%s", name))
	if err != nil {
		return fmt.Errorf("create temp file for %s: %w", name, err)
	}
	defer func() {
		if err := tempFile.Close(); err != nil {
			log.Error(ctx, "close temp file", "err", err)
		}
		if err := os.Remove(tempFile.Name()); err != nil && !errors.Is(err, os.ErrNotExist) {
			log.Error(ctx, "remove temp file", "err", err)
		}
	}()

	log.Debug(ctx, "downloading", "path", path, "url", url)
	ctx, cancel := context.WithTimeout(ctx, downloadTimeout)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return fmt.Errorf("create download request: %w", err)
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return fmt.Errorf("execute download request: %w", err)
	}

	defer func() {
		err := resp.Body.Close()
		if err != nil {
			log.Error(ctx, "downloadFile: close body error", "err", err)
		}
	}()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("unexpected status code %s downloading %s from %s", resp.Status, name, url)
	}

	written, err := io.Copy(tempFile, resp.Body)
	if err != nil {
		log.Error(ctx, "download file", "err", err, "bytes", written, "total", resp.ContentLength)
		if err := os.Remove(tempFile.Name()); err != nil {
			log.Error(ctx, "remove temp file", "err", err)
		}
		return fmt.Errorf("copy %s: %w", name, err)
	}
	log.Debug(ctx, "file has been downloaded", "path", path, "bytes", written)

	if err := tempFile.Chmod(mode); err != nil {
		return fmt.Errorf("chmod %s: %w", path, err)
	}

	if err := os.Rename(tempFile.Name(), path); err != nil {
		return fmt.Errorf("move %s to %s: %w", name, path, err)
	}

	return nil
}

func checkDstackComponent(ctx context.Context, name ComponentName, pth string) (status ComponentStatus, version string, err error) {
	exists, err := common.PathExists(pth)
	if err != nil {
		return ComponentStatusError, "", fmt.Errorf("check %s: %w", name, err)
	}
	if !exists {
		return ComponentStatusNotInstalled, "", nil
	}

	cmd := exec.CommandContext(ctx, pth, "--version")
	output, err := cmd.Output()
	if err != nil {
		return ComponentStatusError, "", fmt.Errorf("check %s: %w", name, err)
	}

	rawVersion := string(output) // dstack-{shim,runner} version 0.19.38
	versionFields := strings.Fields(rawVersion)
	if len(versionFields) != 3 {
		return ComponentStatusError, "", fmt.Errorf("check %s: unexpected version output: %s", name, rawVersion)
	}
	if versionFields[0] != string(name) {
		return ComponentStatusError, "", fmt.Errorf("check %s: unexpected component name: %s", name, versionFields[0])
	}
	return ComponentStatusInstalled, versionFields[2], nil
}
