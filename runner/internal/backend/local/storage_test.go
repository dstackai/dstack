package local

import (
	"context"
	"github.com/dstackai/dstack/runner/internal/backend/base"
	"github.com/stretchr/testify/assert"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestListEmptyRoot(t *testing.T) {
	s, err := NewLocalTest(t.TempDir(), []string{})
	assert.Nil(t, err)
	items, err := base.ListObjects(context.TODO(), s, "")
	assert.Nil(t, err)
	assert.ElementsMatch(t, items, []string{})
}

func TestListNotExist(t *testing.T) {
	s, err := NewLocalTest(t.TempDir(), []string{})
	assert.Nil(t, err)
	items, err := base.ListObjects(context.TODO(), s, "a/b/c")
	assert.Nil(t, err)
	assert.ElementsMatch(t, items, []string{})
}

func TestListRecursive(t *testing.T) {
	s, err := NewLocalTest(t.TempDir(), []string{
		"a/b/c",
		"a/d",
		"b/c",
		"a/x/",
	})
	assert.Nil(t, err)
	items, err := base.ListObjects(context.TODO(), s, "a")
	assert.Nil(t, err)
	assert.ElementsMatch(t, items, []string{"a/b/c", "a/d"})
}

func TestListPrefix(t *testing.T) {
	s, err := NewLocalTest(t.TempDir(), []string{
		"a/1234",
		"a/12qw",
		"a/12/3x",
		"a/1123",
		"a/qwerty",
	})
	assert.Nil(t, err)
	items, err := base.ListObjects(context.TODO(), s, "a/12")
	assert.Nil(t, err)
	assert.ElementsMatch(t, items, []string{"a/1234", "a/12qw", "a/12/3x"})
}

func TestListPrefixWithSlash(t *testing.T) {
	s, err := NewLocalTest(t.TempDir(), []string{
		"a/1234",
		"a/12/qwe",
	})
	assert.Nil(t, err)
	items, err := base.ListObjects(context.TODO(), s, "a/12/")
	assert.Nil(t, err)
	assert.ElementsMatch(t, items, []string{"a/12/qwe"})
}

func NewLocalTest(root string, files []string) (*LocalStorage, error) {
	for _, file := range files {
		path := filepath.Join(root, file)
		if strings.HasSuffix(file, "/") { // create dir
			if err := os.MkdirAll(path, 0o755); err != nil {
				return nil, err
			}
		} else { // create file
			if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
				return nil, err
			}
			if err := os.WriteFile(path, []byte(file), 0o644); err != nil {
				return nil, err
			}
		}
	}
	return &LocalStorage{basepath: root}, nil
}
