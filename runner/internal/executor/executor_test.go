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
	"testing"
	"time"

	"github.com/dstackai/dstack/runner/internal/schemas"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// todo test get history

func TestExecutor_WorkingDir_Current(t *testing.T) {
	var b bytes.Buffer
	ex := makeTestExecutor(t)
	workingDir := "."
	ex.jobSpec.WorkingDir = &workingDir
	ex.jobSpec.Commands = append(ex.jobSpec.Commands, "pwd")

	err := ex.execJob(context.TODO(), io.Writer(&b))
	assert.NoError(t, err)
	assert.Equal(t, ex.workingDir+"\r\n", b.String())
}

func TestExecutor_WorkingDir_Nil(t *testing.T) {
	var b bytes.Buffer
	ex := makeTestExecutor(t)
	ex.jobSpec.WorkingDir = nil
	ex.jobSpec.Commands = append(ex.jobSpec.Commands, "pwd")

	err := ex.execJob(context.TODO(), io.Writer(&b))
	assert.NoError(t, err)
	assert.Equal(t, ex.workingDir+"\r\n", b.String())
}

func TestExecutor_HomeDir(t *testing.T) {
	var b bytes.Buffer
	ex := makeTestExecutor(t)
	ex.jobSpec.Commands = append(ex.jobSpec.Commands, "echo ~")

	err := ex.execJob(context.TODO(), io.Writer(&b))
	assert.NoError(t, err)
	assert.Equal(t, ex.homeDir+"\r\n", b.String())
}

func TestExecutor_NonZeroExit(t *testing.T) {
	ex := makeTestExecutor(t)
	ex.jobSpec.Commands = append(ex.jobSpec.Commands, "ehco 1") // note: intentional misspelling

	err := ex.execJob(context.TODO(), io.Discard)
	assert.Error(t, err)
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
	assert.Equal(t, "bar\r\n", b.String())
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
	ex.run.RepoData = schemas.RepoData{
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
	expected := fmt.Sprintf("%s\r\n%s\r\n%s\r\n", ex.run.RepoData.RepoHash, ex.run.RepoData.RepoConfigName, ex.run.RepoData.RepoConfigEmail)
	assert.Equal(t, expected, b.String())
}

/* Helpers */

func makeTestExecutor(t *testing.T) *RunExecutor {
	t.Helper()
	baseDir, err := filepath.EvalSymlinks(t.TempDir())
	workingDir := "."
	require.NoError(t, err)

	body := schemas.SubmitBody{
		RunSpec: schemas.RunSpec{
			RunName:  "red-turtle-1",
			RepoId:   "test-000000",
			RepoData: schemas.RepoData{RepoType: "local"},
			Configuration: schemas.Configuration{
				Type: "task",
			},
			ConfigurationPath: ".dstack.yml",
		},
		JobSpec: schemas.JobSpec{
			Commands:    []string{"/bin/bash", "-c"},
			Env:         make(map[string]string),
			MaxDuration: 0, // no timeout
			WorkingDir:  &workingDir,
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
