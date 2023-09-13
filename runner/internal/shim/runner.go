package shim

import (
	"fmt"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"io"
	"net/http"
	"os"
	"strconv"
	"strings"
)

const (
	DstackRunnerURL     = "https://%s.s3.eu-west-1.amazonaws.com/%s/binaries/dstack-runner-linux-amd64"
	DstackReleaseBucket = "dstack-runner-downloads"
	DstackStagingBucket = "dstack-runner-downloads-stgn"
)

func (c *RunnerParameters) GetDockerCommands() []string {
	binaryPath := "/usr/local/bin/dstack-runner"
	return []string{
		// download runner
		fmt.Sprintf("curl --output %s %s", binaryPath, c.getRunnerURL()),
		fmt.Sprintf("chmod +x %s", binaryPath),
		// start runner
		fmt.Sprintf("%s %s", binaryPath, strings.Join(c.getRunnerArgs(), " ")),
	}
}

func (c *RunnerParameters) getRunnerArgs() []string {
	return []string{
		"--log-level", strconv.Itoa(c.LogLevel),
		"start",
		"--http-port", strconv.Itoa(c.HttpPort),
		"--temp-dir", c.TempDir,
		"--home-dir", c.HomeDir,
		"--working-dir", c.WorkingDir,
	}
}

func (c *RunnerParameters) getRunnerURL() string {
	if c.UseDev {
		return fmt.Sprintf(DstackRunnerURL, DstackStagingBucket, c.RunnerVersion)
	}
	return fmt.Sprintf(DstackRunnerURL, DstackReleaseBucket, c.RunnerVersion)
}

func downloadRunner(runnerVersion string, useDev bool, path string) error {
	var url string
	if useDev {
		url = fmt.Sprintf(DstackRunnerURL, DstackStagingBucket, runnerVersion)
	} else {
		url = fmt.Sprintf(DstackRunnerURL, DstackReleaseBucket, runnerVersion)
	}

	file, err := os.Create(path)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = file.Close() }()

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
