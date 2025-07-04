package executor

import (
	"archive/tar"
	"bytes"
	"context"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/dstackai/dstack/runner/internal/schemas"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestExecutor_WorkingDir_Current(t *testing.T) {
	var b bytes.Buffer
	ex := makeTestExecutor(t)
	workingDir := "."
	ex.jobSpec.WorkingDir = &workingDir
	ex.jobSpec.Commands = append(ex.jobSpec.Commands, "pwd")

	err := ex.execJob(context.TODO(), io.Writer(&b))
	assert.NoError(t, err)
	// Normalize line endings for cross-platform compatibility.
	assert.Equal(t, ex.workingDir+"\n", strings.ReplaceAll(b.String(), "\r\n", "\n"))
}

func TestExecutor_WorkingDir_Nil(t *testing.T) {
	var b bytes.Buffer
	ex := makeTestExecutor(t)
	ex.jobSpec.WorkingDir = nil
	ex.jobSpec.Commands = append(ex.jobSpec.Commands, "pwd")

	err := ex.execJob(context.TODO(), io.Writer(&b))
	assert.NoError(t, err)
	assert.Equal(t, ex.workingDir+"\n", strings.ReplaceAll(b.String(), "\r\n", "\n"))
}

func TestExecutor_HomeDir(t *testing.T) {
	var b bytes.Buffer
	ex := makeTestExecutor(t)
	ex.jobSpec.Commands = append(ex.jobSpec.Commands, "echo ~")

	err := ex.execJob(context.TODO(), io.Writer(&b))
	assert.NoError(t, err)
	assert.Equal(t, ex.homeDir+"\n", strings.ReplaceAll(b.String(), "\r\n", "\n"))
}

func TestExecutor_NonZeroExit(t *testing.T) {
	ex := makeTestExecutor(t)
	ex.jobSpec.Commands = append(ex.jobSpec.Commands, "exit 100")
	makeCodeTar(t, ex.codePath)

	err := ex.Run(context.TODO())
	assert.Error(t, err)
	assert.NotEmpty(t, ex.jobStateHistory)
	exitStatus := ex.jobStateHistory[len(ex.jobStateHistory)-1].ExitStatus
	assert.NotNil(t, exitStatus)
	assert.Equal(t, 100, *exitStatus)
}

func TestExecutor_SSHCredentials(t *testing.T) {
	key := "== ssh private key =="

	var b bytes.Buffer
	ex := makeTestExecutor(t)
	ex.jobSpec.Commands = append(ex.jobSpec.Commands, "cat ~/.ssh/id_rsa")
	ex.repoCredentials = &schemas.RepoCredentials{
		CloneURL:   "ssh://git@github.com/dstackai/dstack-examples.git",
		PrivateKey: &key,
	}

	clean, err := ex.setupCredentials(context.TODO())
	defer clean()
	require.NoError(t, err)

	err = ex.execJob(context.TODO(), io.Writer(&b))
	assert.NoError(t, err)
	assert.Equal(t, key, b.String())
}

func TestExecutor_LocalRepo(t *testing.T) {
	var b bytes.Buffer
	ex := makeTestExecutor(t)
	ex.jobSpec.Commands = append(ex.jobSpec.Commands, "cat foo")
	makeCodeTar(t, ex.codePath)

	err := ex.setupRepo(context.TODO())
	require.NoError(t, err)

	err = ex.execJob(context.TODO(), io.Writer(&b))
	assert.NoError(t, err)
	assert.Equal(t, "bar\n", strings.ReplaceAll(b.String(), "\r\n", "\n"))
}

func TestExecutor_Recover(t *testing.T) {
	ex := makeTestExecutor(t)
	ex.jobSpec.Commands = nil // cause a panic
	makeCodeTar(t, ex.codePath)

	err := ex.Run(context.TODO())
	assert.ErrorContains(t, err, "recovered: ")
}

/* Long tests */

func TestExecutor_MaxDuration(t *testing.T) {
	if testing.Short() {
		t.Skip()
	}

	ex := makeTestExecutor(t)
	ex.killDelay = 500 * time.Millisecond
	ex.jobSpec.Commands = append(ex.jobSpec.Commands, "echo 1 && sleep 2 && echo 2")
	ex.jobSpec.MaxDuration = 1 // seconds
	makeCodeTar(t, ex.codePath)

	err := ex.Run(context.TODO())
	assert.ErrorContains(t, err, "killed")
}

func TestExecutor_RemoteRepo(t *testing.T) {
	if testing.Short() {
		t.Skip()
	}

	var b bytes.Buffer
	ex := makeTestExecutor(t)
	ex.jobSpec.RepoData = &schemas.RepoData{
		RepoType:        "remote",
		RepoBranch:      "main",
		RepoHash:        "2b83592e506ed6fe8e49f4eaa97c3866bc9402b1",
		RepoConfigName:  "Dstack Developer",
		RepoConfigEmail: "developer@dstack.ai",
	}
	ex.jobSpec.Commands = append(ex.jobSpec.Commands, "git rev-parse HEAD && git config user.name && git config user.email")
	err := os.WriteFile(ex.codePath, []byte{}, 0o600) // empty diff
	require.NoError(t, err)

	err = ex.setupRepo(context.TODO())
	require.NoError(t, err)

	err = ex.execJob(context.TODO(), io.Writer(&b))
	assert.NoError(t, err)
	expected := fmt.Sprintf("%s\n%s\n%s\n", ex.getRepoData().RepoHash, ex.getRepoData().RepoConfigName, ex.getRepoData().RepoConfigEmail)
	assert.Equal(t, expected, strings.ReplaceAll(b.String(), "\r\n", "\n"))
}

/* Helpers */

func makeTestExecutor(t *testing.T) *RunExecutor {
	t.Helper()
	baseDir, err := filepath.EvalSymlinks(t.TempDir())
	workingDir := "."
	require.NoError(t, err)

	body := schemas.SubmitBody{
		Run: schemas.Run{
			Id: "12346",
			RunSpec: schemas.RunSpec{
				RunName:  "red-turtle-1",
				RepoId:   "test-000000",
				RepoData: schemas.RepoData{RepoType: "local"},
				Configuration: schemas.Configuration{
					Type: "task",
				},
				ConfigurationPath: ".dstack.yml",
			},
		},
		JobSpec: schemas.JobSpec{
			Commands:    []string{"/bin/bash", "-c"},
			Env:         make(map[string]string),
			MaxDuration: 0, // no timeout
			WorkingDir:  &workingDir,
			RepoData:    &schemas.RepoData{RepoType: "local"},
		},
		Secrets: make(map[string]string),
		RepoCredentials: &schemas.RepoCredentials{
			CloneURL: "https://github.com/dstackai/dstack-examples.git",
		},
	}

	temp := filepath.Join(baseDir, "temp")
	_ = os.Mkdir(temp, 0o700)
	home := filepath.Join(baseDir, "home")
	_ = os.Mkdir(home, 0o700)
	repo := filepath.Join(baseDir, "repo")
	_ = os.Mkdir(repo, 0o700)
	ex, _ := NewRunExecutor(temp, home, repo, 10022)
	ex.SetJob(body)
	ex.SetCodePath(filepath.Join(baseDir, "code")) // note: create file before run
	return ex
}

func makeCodeTar(t *testing.T, path string) {
	t.Helper()
	file, err := os.Create(path)
	require.NoError(t, err)
	defer func() { _ = file.Close() }()
	tw := tar.NewWriter(file)

	files := []struct{ name, body string }{
		{"foo", "bar\n"},
	}

	for _, f := range files {
		hdr := &tar.Header{Name: f.name, Mode: 0o600, Size: int64(len(f.body))}
		require.NoError(t, tw.WriteHeader(hdr))
		_, err := tw.Write([]byte(f.body))
		require.NoError(t, err)
	}
	require.NoError(t, tw.Close())
}

func TestWriteDstackProfile(t *testing.T) {
	testCases := []string{
		"",
		"string 'with 'single' quotes",
		"multi\nline\tstring",
	}
	tmp := t.TempDir()
	path := tmp + "/dstack_profile"
	script := fmt.Sprintf(`. '%s'; printf '%%s' "$VAR"`, path)
	for _, value := range testCases {
		env := map[string]string{"VAR": value}
		writeDstackProfile(env, path)
		cmd := exec.Command("/bin/sh", "-c", script)
		out, err := cmd.Output()
		assert.NoError(t, err)
		assert.Equal(t, value, string(out))
	}
}

func TestExecutor_Logs(t *testing.T) {
	var b bytes.Buffer
	ex := makeTestExecutor(t)
	// Use printf to generate ANSI control codes.
	// \033[31m = red text, \033[1;32m = bold green text, \033[0m = reset
	ex.jobSpec.Commands = append(ex.jobSpec.Commands, "printf '\\033[31mRed Hello World\\033[0m\\n' && printf '\\033[1;32mBold Green Line 2\\033[0m\\n' && printf 'Line 3\\n'")

	err := ex.execJob(context.TODO(), io.Writer(&b))
	assert.NoError(t, err)

	logHistory := ex.GetHistory(0).JobLogs
	assert.NotEmpty(t, logHistory)

	logString := combineLogMessages(logHistory)
	normalizedLogString := strings.ReplaceAll(logString, "\r\n", "\n")

	expectedOutput := "Red Hello World\nBold Green Line 2\nLine 3\n"
	assert.Equal(t, expectedOutput, normalizedLogString, "Should strip ANSI codes from regular logs")

	// Verify timestamps are in order
	assert.Greater(t, len(logHistory), 0)
	for i := 1; i < len(logHistory); i++ {
		assert.GreaterOrEqual(t, logHistory[i].Timestamp, logHistory[i-1].Timestamp)
	}
}

func TestExecutor_LogsWithErrors(t *testing.T) {
	var b bytes.Buffer
	ex := makeTestExecutor(t)
	ex.jobSpec.Commands = append(ex.jobSpec.Commands, "echo 'Success message' && echo 'Error message' >&2 && exit 1")

	err := ex.execJob(context.TODO(), io.Writer(&b))
	assert.Error(t, err)

	logHistory := ex.GetHistory(0).JobLogs
	assert.NotEmpty(t, logHistory)

	logString := combineLogMessages(logHistory)
	normalizedLogString := strings.ReplaceAll(logString, "\r\n", "\n")

	expectedOutput := "Success message\nError message\n"
	assert.Equal(t, expectedOutput, normalizedLogString)
}

func TestExecutor_LogsAnsiCodeHandling(t *testing.T) {
	var b bytes.Buffer
	ex := makeTestExecutor(t)

	// Test a variety of ANSI escape sequences on stdout and stderr.
	cmd := "printf '\\033[31mRed\\033[0m \\033[32mGreen\\033[0m\\n' && " +
		"printf '\\033[1mBold\\033[0m \\033[4mUnderline\\033[0m\\n' && " +
		"printf '\\033[s\\033[uPlain text\\n' >&2"

	ex.jobSpec.Commands = append(ex.jobSpec.Commands, cmd)

	err := ex.execJob(context.TODO(), io.Writer(&b))
	assert.NoError(t, err)

	// 1. Check WebSocket logs, which should preserve ANSI codes.
	wsLogHistory := ex.GetJobWsLogsHistory()
	assert.NotEmpty(t, wsLogHistory)
	wsLogString := combineLogMessages(wsLogHistory)
	normalizedWsLogString := strings.ReplaceAll(wsLogString, "\r\n", "\n")

	expectedWsOutput := "\033[31mRed\033[0m \033[32mGreen\033[0m\n" +
		"\033[1mBold\033[0m \033[4mUnderline\033[0m\n" +
		"\033[s\033[uPlain text\n"
	assert.Equal(t, expectedWsOutput, normalizedWsLogString, "Websocket logs should preserve ANSI codes")

	// 2. Check regular job logs, which should have ANSI codes stripped.
	regularLogHistory := ex.GetHistory(0).JobLogs
	assert.NotEmpty(t, regularLogHistory)
	regularLogString := combineLogMessages(regularLogHistory)
	normalizedRegularLogString := strings.ReplaceAll(regularLogString, "\r\n", "\n")

	expectedRegularOutput := "Red Green\n" +
		"Bold Underline\n" +
		"Plain text\n"
	assert.Equal(t, expectedRegularOutput, normalizedRegularLogString, "Regular logs should have ANSI codes stripped")

	// Verify timestamps are ordered for both log types.
	assert.Greater(t, len(wsLogHistory), 0)
	for i := 1; i < len(wsLogHistory); i++ {
		assert.GreaterOrEqual(t, wsLogHistory[i].Timestamp, wsLogHistory[i-1].Timestamp)
	}
}

func combineLogMessages(logHistory []schemas.LogEvent) string {
	var logOutput bytes.Buffer
	for _, logEvent := range logHistory {
		logOutput.Write(logEvent.Message)
	}
	return logOutput.String()
}
