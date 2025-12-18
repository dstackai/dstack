package common

import (
	"context"
	"os"
	"path"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestExpandPath_NoPath_NoBase(t *testing.T) {
	path, err := ExpandPath("", "", "")
	require.NoError(t, err)
	require.Equal(t, ".", path)
}

func TestExpandPath_NoPath_RelBase(t *testing.T) {
	testCases := []string{"repo", "./repo"}
	for _, base := range testCases {
		path, err := ExpandPath("", base, "")
		require.NoError(t, err)
		require.Equal(t, "repo", path)
	}
}

func TestExpandPath_NoPath_AbsBase(t *testing.T) {
	path, err := ExpandPath("", "/repo", "")
	require.NoError(t, err)
	require.Equal(t, "/repo", path)
}

func TestExpandtPath_RelPath_NoBase(t *testing.T) {
	testCases := []string{"repo", "./repo"}
	for _, pth := range testCases {
		path, err := ExpandPath(pth, "", "")
		require.NoError(t, err)
		require.Equal(t, "repo", path)
	}
}

func TestExpandtPath_RelPath_RelBase(t *testing.T) {
	path, err := ExpandPath("repo", "data", "")
	require.NoError(t, err)
	require.Equal(t, "data/repo", path)
}

func TestExpandtPath_RelPath_AbsBase(t *testing.T) {
	path, err := ExpandPath("repo", "/data", "")
	require.NoError(t, err)
	require.Equal(t, "/data/repo", path)
}

func TestExpandtPath_AbsPath_NoBase(t *testing.T) {
	path, err := ExpandPath("/repo", "", "")
	require.NoError(t, err)
	require.Equal(t, "/repo", path)
}

func TestExpandtPath_AbsPath_RelBase(t *testing.T) {
	path, err := ExpandPath("/repo", "data", "")
	require.NoError(t, err)
	require.Equal(t, "/repo", path)
}

func TestExpandtPath_AbsPath_AbsBase(t *testing.T) {
	path, err := ExpandPath("/repo", "/data", "")
	require.NoError(t, err)
	require.Equal(t, "/repo", path)
}

func TestExpandPath_BareTilde_NoHome(t *testing.T) {
	path, err := ExpandPath("~", "", "")
	require.NoError(t, err)
	require.Equal(t, ".", path)
}

func TestExpandPath_BareTilde_RelHome(t *testing.T) {
	path, err := ExpandPath("~", "", "user")
	require.NoError(t, err)
	require.Equal(t, "user", path)
}

func TestExpandPath_BareTilde_AbsHome(t *testing.T) {
	path, err := ExpandPath("~", "", "/home/user")
	require.NoError(t, err)
	require.Equal(t, "/home/user", path)
}

func TestExpandtPath_TildeWithPath_NoHome(t *testing.T) {
	path, err := ExpandPath("~/repo", "", "")
	require.NoError(t, err)
	require.Equal(t, "repo", path)
}

func TestExpandtPath_TildeWithPath_RelHome(t *testing.T) {
	path, err := ExpandPath("~/repo", "", "user")
	require.NoError(t, err)
	require.Equal(t, "user/repo", path)
}

func TestExpandtPath_TildeWithPath_AbsHome(t *testing.T) {
	path, err := ExpandPath("~/repo", "", "/home/user")
	require.NoError(t, err)
	require.Equal(t, "/home/user/repo", path)
}

func TestExpandtPath_ErrorTildeUsernameNotSupported_BareTildeUsername(t *testing.T) {
	path, err := ExpandPath("~username", "", "")
	require.ErrorContains(t, err, "~username syntax is not supported")
	require.Equal(t, "", path)
}

func TestExpandtPath_ErrorTildeUsernameNotSupported_TildeUsernameWithPath(t *testing.T) {
	path, err := ExpandPath("~username/repo", "", "")
	require.ErrorContains(t, err, "~username syntax is not supported")
	require.Equal(t, "", path)
}

func TestMkdirAll_AbsPath_NotExists(t *testing.T) {
	absPath := path.Join(t.TempDir(), "a/b/c")
	require.NoDirExists(t, absPath)
	err := MkdirAll(context.Background(), absPath, -1, -1)
	require.NoError(t, err)
	require.DirExists(t, absPath)
}

func TestMkdirAll_AbsPath_Exists(t *testing.T) {
	absPath, err := os.Getwd()
	require.NoError(t, err)
	err = MkdirAll(context.Background(), absPath, -1, -1)
	require.NoError(t, err)
	require.DirExists(t, absPath)
}

func TestMkdirAll_RelPath_NotExists(t *testing.T) {
	cwd := t.TempDir()
	os.Chdir(cwd)
	relPath := "a/b/c"
	absPath := path.Join(cwd, relPath)
	require.NoDirExists(t, absPath)
	err := MkdirAll(context.Background(), relPath, -1, -1)
	require.NoError(t, err)
	require.DirExists(t, absPath)
}

func TestMkdirAll_RelPath_Exists(t *testing.T) {
	cwd := t.TempDir()
	os.Chdir(cwd)
	relPath := "a/b/c"
	absPath := path.Join(cwd, relPath)
	err := os.MkdirAll(absPath, 0o755)
	require.NoError(t, err)
	err = MkdirAll(context.Background(), relPath, -1, -1)
	require.NoError(t, err)
	require.DirExists(t, absPath)
}
