package shim

import (
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	rt "runtime"
	"strconv"
	"strings"

	"github.com/dstackai/dstack/runner/internal/gerrors"
)

const (
	DstackRunnerURL        = "https://%s.s3.eu-west-1.amazonaws.com/%s/binaries/dstack-runner-%s-%s"
	DstackReleaseBucket    = "dstack-runner-downloads"
	DstackStagingBucket    = "dstack-runner-downloads-stgn"
	DstackRunnerBinaryName = "/usr/local/bin/dstack-runner"
)

func (c *CLIArgs) GetDockerCommands() []string {
	return []string{
		// start runner
		fmt.Sprintf("%s %s", DstackRunnerBinaryName, strings.Join(c.getRunnerArgs(), " ")),
	}
}

func (c *CLIArgs) Download(osName string) error {
	tempFile, err := os.CreateTemp("", "dstack-runner")
	if err != nil {
		return gerrors.Wrap(err)
	}
	if err = tempFile.Close(); err != nil {
		return gerrors.Wrap(err)
	}
	c.Runner.BinaryPath = tempFile.Name()
	return gerrors.Wrap(downloadRunner(c.Runner.Version, c.Runner.DevChannel, osName, c.Runner.BinaryPath))
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

func downloadRunner(runnerVersion string, useDev bool, osName string, path string) error {
	// darwin-amd64
	// darwin-arm64
	// linux-386
	// linux-amd64
	archName := rt.GOARCH
	if osName == "linux" && archName == "arm64" {
		archName = "amd64"
	}
	var url string
	if useDev {
		url = fmt.Sprintf(DstackRunnerURL, DstackStagingBucket, runnerVersion, osName, archName)
	} else {
		url = fmt.Sprintf(DstackRunnerURL, DstackReleaseBucket, runnerVersion, osName, archName)
	}

	file, err := os.Create(path)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = file.Close() }()

	log.Printf("Downloading runner from %s\n", url)
	resp, err := http.Get(url)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode != http.StatusOK {
		return gerrors.Newf("unexpected status code: %s", resp.Status)
	}

	_, err = io.Copy(file, resp.Body)
	if err != nil {
		return gerrors.Wrap(err)
	}

	return gerrors.Wrap(file.Chmod(0755))
}
