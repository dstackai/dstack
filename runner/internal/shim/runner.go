package shim

import (
	"context"
	"errors"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"time"

	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
)

func (c *CLIArgs) DownloadRunner(ctx context.Context) error {
	if c.Runner.DownloadURL == "" {
		return nil
	}
	err := downloadRunner(ctx, c.Runner.DownloadURL, c.Runner.BinaryPath, false)
	if err != nil {
		return gerrors.Wrap(err)
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
		"--working-dir", consts.RunnerWorkingDir,
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
		return gerrors.Wrap(err)
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
		return gerrors.Wrap(err)
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() {
		err := resp.Body.Close()
		if err != nil {
			log.Error(ctx, "downloadRunner: close body error", "err", err)
		}
	}()

	if resp.StatusCode != http.StatusOK {
		return gerrors.Newf("unexpected status code: %s", resp.Status)
	}

	written, err := io.Copy(tempFile, resp.Body)
	if err != nil {
		return gerrors.Wrap(err)
	}

	select {
	case <-ctx.Done():
		err := ctx.Err()
		if errors.Is(err, context.DeadlineExceeded) {
			log.Error(ctx, "downloadRunner error", "err", err, "bytes", written, "total", resp.ContentLength)
			return gerrors.Newf("Cannot download runner %w", err)
		}
	default:
		log.Info(ctx, "the runner was downloaded successfully", "bytes", written)
	}

	if err := tempFile.Chmod(0o755); err != nil {
		return gerrors.Wrap(err)
	}

	if err := os.Rename(tempFile.Name(), path); err != nil {
		return gerrors.Wrap(err)
	}

	return nil
}
