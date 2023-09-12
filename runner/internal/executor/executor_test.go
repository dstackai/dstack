package executor

import (
	"bytes"
	"context"
	"fmt"
	"github.com/dstackai/dstack/runner/internal/schemas"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"io"
	"os"
	"path/filepath"
	"testing"
)

// todo should we test context cancellation?

// todo test local repo (tar)
// todo test get history

func TestExecutor_WorkingDir(t *testing.T) {
	var b bytes.Buffer
	ex := makeTestExecutor(t)
	ex.jobSpec.Commands = []string{"pwd"}

	err := ex.execJob(context.TODO(), io.Writer(&b))
	assert.NoError(t, err)
	assert.Equal(t, ex.workingDir+"\n", b.String())
}

func TestExecutor_HomeDir(t *testing.T) {
	var b bytes.Buffer
	ex := makeTestExecutor(t)
	ex.jobSpec.Commands = []string{"echo ~"}

	err := ex.execJob(context.TODO(), io.Writer(&b))
	assert.NoError(t, err)
	assert.Equal(t, ex.homeDir+"\n", b.String())
}

func TestExecutor_NonZeroExit(t *testing.T) {
	ex := makeTestExecutor(t)
	ex.jobSpec.Commands = []string{"ehco 1"} // note: intentional misspelling

	err := ex.execJob(context.TODO(), io.Discard)
	assert.Error(t, err)
}

func TestExecutor_SSHCredentials(t *testing.T) {
	key := "== ssh private key =="

	var b bytes.Buffer
	ex := makeTestExecutor(t)
	ex.jobSpec.Commands = []string{"cat ~/.ssh/id_rsa"}
	ex.repoCredentials = &schemas.RepoCredentials{
		Protocol:   "ssh",
		PrivateKey: &key,
	}

	clean, err := ex.setupCredentials(context.TODO())
	defer clean()
	require.NoError(t, err)

	err = ex.execJob(context.TODO(), io.Writer(&b))
	assert.NoError(t, err)
	assert.Equal(t, key, b.String())
}

func TestExecutor_RemoteRepo(t *testing.T) {
	if testing.Short() {
		t.Skip()
	}

	var b bytes.Buffer
	ex := makeTestExecutor(t)
	ex.jobSpec.Commands = []string{"git rev-parse HEAD", "git config user.name", "git config user.email"}
	ex.repoCredentials = &schemas.RepoCredentials{Protocol: "https"}
	ex.run.RepoData = schemas.RepoData{
		RepoType:        "remote",
		RepoHostName:    "github.com",
		RepoPort:        0,
		RepoUserName:    "dstackai",
		RepoName:        "dstack-examples",
		RepoBranch:      "main",
		RepoHash:        "2b83592e506ed6fe8e49f4eaa97c3866bc9402b1",
		RepoConfigName:  "Dstack Developer",
		RepoConfigEmail: "developer@dstack.ai",
	}
	err := os.WriteFile(ex.codePath, []byte{}, 0600) // empty diff
	require.NoError(t, err)

	err = ex.setupRepo(context.TODO())
	require.NoError(t, err)

	err = ex.execJob(context.TODO(), io.Writer(&b))
	assert.NoError(t, err)
	expected := fmt.Sprintf("%s\n%s\n%s\n", ex.run.RepoData.RepoHash, ex.run.RepoData.RepoConfigName, ex.run.RepoData.RepoConfigEmail)
	assert.Equal(t, expected, b.String())
}

func makeTestExecutor(t *testing.T) *Executor {
	t.Helper()
	baseDir, err := filepath.EvalSymlinks(t.TempDir())
	require.NoError(t, err)

	body := schemas.SubmitBody{
		Run: schemas.Run{
			Id:      "test",
			RunName: "red-turtle-1",
			RepoId:  "test-000000",
			RepoData: schemas.RepoData{
				RepoType: "local",
			},
			Configuration: schemas.Configuration{
				Type: "task",
			},
			ConfigurationPath: ".dstack.yml",
		},
		JobSpec: schemas.JobSpec{
			Commands:    nil, // note: fill before run
			Entrypoint:  []string{"/bin/bash", "-c"},
			Env:         make(map[string]string),
			MaxDuration: 0, // no timeout
			WorkingDir:  ".",
		},
		Secrets: make(map[string]string),
	}

	temp := filepath.Join(baseDir, "temp")
	_ = os.Mkdir(temp, 0700)
	home := filepath.Join(baseDir, "home")
	_ = os.Mkdir(home, 0700)
	repo := filepath.Join(baseDir, "repo")
	_ = os.Mkdir(repo, 0700)
	ex := NewExecutor(temp, home, repo)
	ex.SetJob(body)
	ex.SetCodePath(filepath.Join(baseDir, "code")) // note: create file before run
	return ex
}
