package local

import (
	"os"
	"path/filepath"
	"strings"

	"github.com/dstackai/dstack/runner/internal/gerrors"
)

type LocalStorage struct {
	basepath string
}

func NewLocalStorage(path string) *LocalStorage {
	return &LocalStorage{basepath: path}
}

func (lstorage *LocalStorage) GetFile(path string) ([]byte, error) {
	fullpath := filepath.Join(lstorage.basepath, path)
	contents, err := os.ReadFile(fullpath)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return contents, nil
}

func (lstorage *LocalStorage) PutFile(path string, contents []byte) error {
	fullpath := filepath.Join(lstorage.basepath, path)
	err := os.WriteFile(fullpath, contents, 0644)
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (lstorage *LocalStorage) RenameFile(oldKey, newKey string) error {
	if oldKey == newKey {
		return nil
	}
	tmpfile, err := os.CreateTemp(filepath.Join(lstorage.basepath, "tmp"), "job")
	if err != nil {
		return gerrors.Wrap(err)
	}
	contents, err := lstorage.GetFile(oldKey)
	if err != nil {
		return gerrors.Wrap(err)
	}
	_, err = tmpfile.Write(contents)
	if err != nil {
		return gerrors.Wrap(err)
	}
	err = tmpfile.Close()
	if err != nil {
		return gerrors.Wrap(err)
	}
	err = os.Rename(tmpfile.Name(), filepath.Join(lstorage.basepath, newKey))
	if err != nil {
		return gerrors.Wrap(err)
	}
	err = os.Remove(filepath.Join(lstorage.basepath, oldKey))
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (lstorage *LocalStorage) ListFile(prefix string) ([]string, error) {
	dirpath := filepath.Dir(prefix)
	filePrefix := filepath.Base(prefix)
	entries, err := os.ReadDir(filepath.Join(lstorage.basepath, dirpath))
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	fileNames := make([]string, 0)
	for _, entry := range entries {
		if strings.HasPrefix(entry.Name(), filePrefix) {
			fileNames = append(fileNames, filepath.Join(dirpath, entry.Name()))
		}
	}
	return fileNames, nil
}
