package shim

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
)

const DstackRunnerBinaryName = "/usr/local/bin/dstack-runner"

func (c *CLIArgs) GetDockerCommands() []string {
	return []string{
		// start runner
		fmt.Sprintf("%s %s", DstackRunnerBinaryName, strings.Join(c.getRunnerArgs(), " ")),
	}
}

func (c *CLIArgs) DownloadRunner(ctx context.Context) error {
	runnerBinaryPath, err := downloadRunner(ctx, c.Runner.DownloadURL)
	if err != nil {
		return gerrors.Wrap(err)
	}

	c.Runner.BinaryPath = runnerBinaryPath

	return nil
}

func (c *CLIArgs) getRunnerArgs() []string {
	return []string{
		"--log-level", strconv.Itoa(c.Runner.LogLevel),
		"start",
		"--http-port", strconv.Itoa(c.Runner.HTTPPort),
		"--temp-dir", consts.RunnerTempDir,
		"--home-dir", consts.RunnerHomeDir,
		"--working-dir", consts.RunnerWorkingDir,
	}
}

func downloadRunner(ctx context.Context, url string) (string, error) {
	tempFile, err := os.CreateTemp("", "dstack-runner")
	if err != nil {
		return "", gerrors.Wrap(err)
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
		return "", gerrors.Wrap(err)
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	defer func() {
		err := resp.Body.Close()
		if err != nil {
			log.Error(ctx, "downloadRunner: close body error", "err", err)
		}
	}()

	if resp.StatusCode != http.StatusOK {
		return "", gerrors.Newf("unexpected status code: %s", resp.Status)
	}

	written, err := io.Copy(tempFile, resp.Body)
	if err != nil {
		return "", gerrors.Wrap(err)
	}

	select {
	case <-ctx.Done():
		err := ctx.Err()
		if errors.Is(err, context.DeadlineExceeded) {
			log.Error(ctx, "downloadRunner error", "err", err, "bytes", written, "total", resp.ContentLength)
			return "", gerrors.Newf("Cannot download runner %w", err)
		}
	default:
		log.Debug(ctx, "the runner was downloaded successfully", "bytes", written)
	}

	if err := tempFile.Chmod(0o755); err != nil {
		return "", gerrors.Wrap(err)
	}

	return tempFile.Name(), nil
}
