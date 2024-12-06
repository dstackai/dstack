package shim

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/dstackai/dstack/runner/internal/gerrors"
)

const DstackRunnerBinaryName = "/usr/local/bin/dstack-runner"

func (c *CLIArgs) GetDockerCommands() []string {
	return []string{
		// start runner
		fmt.Sprintf("%s %s", DstackRunnerBinaryName, strings.Join(c.getRunnerArgs(), " ")),
	}
}

func (c *CLIArgs) DownloadRunner() error {
	runnerBinaryPath, err := downloadRunner(c.Runner.DownloadURL)
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
		"--temp-dir", c.Runner.TempDir,
		"--home-dir", c.Runner.HomeDir,
		"--working-dir", c.Runner.WorkingDir,
	}
}

func downloadRunner(url string) (string, error) {
	tempFile, err := os.CreateTemp("", "dstack-runner")
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	defer func() {
		err := tempFile.Close()
		if err != nil {
			log.Printf("close file error: %s\n", err)
		}
	}()

	log.Printf("Downloading runner from %s\n", url)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
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
			log.Printf("downloadRunner: close body error: %s\n", err)
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
			fmt.Printf("downloadRunner: %s, %d bytes out of %d bytes were downloaded", err, written, resp.ContentLength)
			return "", gerrors.Newf("Cannot download runner %w", err)
		}
	default:
		log.Printf("The runner was downloaded successfully (%d bytes)", written)
	}

	if err := tempFile.Chmod(0o755); err != nil {
		return "", gerrors.Wrap(err)
	}

	return tempFile.Name(), nil
}
