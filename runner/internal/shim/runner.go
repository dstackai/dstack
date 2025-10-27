package shim

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"time"

	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/log"
)

func (c *CLIArgs) DownloadRunner(ctx context.Context) error {
	if c.Runner.DownloadURL == "" {
		return nil
	}
	err := downloadRunner(ctx, c.Runner.DownloadURL, c.Runner.BinaryPath, false)
	if err != nil {
		return fmt.Errorf("download runner from %s: %w", c.Runner.DownloadURL, err)
	}
	return nil
}

func (c *CLIArgs) getRunnerArgs() []string {
	return []string{
		"--log-level", strconv.Itoa(c.Runner.LogLevel),
		"start",
		"--http-port", strconv.Itoa(c.Runner.HTTPPort),
		"--ssh-port", strconv.Itoa(c.Runner.SSHPort),
		"--temp-dir", consts.RunnerTempDir,
		"--home-dir", consts.RunnerHomeDir,
	}
}

func downloadRunner(ctx context.Context, url string, path string, force bool) error {
	if _, err := os.Stat(path); err == nil {
		if force {
			log.Info(ctx, "dstack-runner binary exists, forcing download", "path", path)
		} else {
			log.Info(ctx, "dstack-runner binary exists, skipping download", "path", path)
			return nil
		}
	}
	tempFile, err := os.CreateTemp(filepath.Dir(path), "dstack-runner")
	if err != nil {
		return fmt.Errorf("create temp file for runner: %w", err)
	}
	defer func() {
		err := tempFile.Close()
		if err != nil {
			log.Error(ctx, "close file error", "err", err)
		}
	}()

	log.Debug(ctx, "downloading runner", "url", url)
	ctx, cancel := context.WithTimeout(ctx, 10*time.Minute)
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
			log.Error(ctx, "downloadRunner: close body error", "err", err)
		}
	}()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("unexpected status code %s downloading runner from %s", resp.Status, url)
	}

	written, err := io.Copy(tempFile, resp.Body)
	if err != nil {
		return fmt.Errorf("copy runner binary: %w", err)
	}

	select {
	case <-ctx.Done():
		err := ctx.Err()
		if errors.Is(err, context.DeadlineExceeded) {
			log.Error(ctx, "downloadRunner error", "err", err, "bytes", written, "total", resp.ContentLength)
			return fmt.Errorf("download runner timeout after %d/%d bytes: %w", written, resp.ContentLength, err)
		}
	default:
		log.Info(ctx, "the runner was downloaded successfully", "bytes", written)
	}

	if err := tempFile.Chmod(0o755); err != nil {
		return fmt.Errorf("chmod runner binary: %w", err)
	}

	if err := os.Rename(tempFile.Name(), path); err != nil {
		return fmt.Errorf("move runner binary to %s: %w", path, err)
	}

	return nil
}
