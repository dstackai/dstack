package local

import (
	"context"
	"errors"
	"github.com/dstackai/dstack/runner/internal/backend/base"
	"io"
	"io/fs"
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

func (s *LocalStorage) Download(ctx context.Context, key string, writer io.Writer) error {
	path := filepath.Join(s.basepath, key)
	file, err := os.Open(path)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = file.Close() }()
	_, err = io.Copy(writer, file)
	return gerrors.Wrap(err)
}

func (s *LocalStorage) Upload(ctx context.Context, reader io.Reader, key string) error {
	tmpfile, err := os.CreateTemp(filepath.Join(s.basepath, "tmp"), "job")
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = os.Remove(tmpfile.Name()) }()
	_, err = io.Copy(tmpfile, reader)
	if err != nil {
		return gerrors.Wrap(err)
	}
	dstPath := filepath.Join(s.basepath, key)
	if err := os.MkdirAll(filepath.Dir(dstPath), 0o755); err != nil {
		return gerrors.Wrap(err)
	}
	return gerrors.Wrap(os.Rename(tmpfile.Name(), dstPath))
}

func (s *LocalStorage) Delete(ctx context.Context, key string) error {
	return gerrors.Wrap(os.Remove(filepath.Join(s.basepath, key)))
}

func (s *LocalStorage) Rename(ctx context.Context, oldKey, newKey string) error {
	if oldKey == newKey {
		return nil
	}

	reader, err := os.Open(filepath.Join(s.basepath, oldKey))
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = reader.Close() }()

	// Upload will create temp file on the same device and afterward replace newKey with oldKey copy
	if err = s.Upload(ctx, reader, newKey); err != nil {
		return gerrors.Wrap(err)
	}
	return gerrors.Wrap(os.Remove(filepath.Join(s.basepath, oldKey)))
}

func (s *LocalStorage) CreateSymlink(ctx context.Context, key, symlink string) error {
	return gerrors.Wrap(os.Symlink(symlink, key))
}

func (s *LocalStorage) GetMetadata(ctx context.Context, key, tag string) (string, error) {
	return "", gerrors.New("not implemented")
}

func (s *LocalStorage) List(ctx context.Context, prefix string) (<-chan *base.StorageObject, <-chan error) {
	dirpath := filepath.Dir(filepath.Join(s.basepath, prefix))
	ch := make(chan *base.StorageObject)
	errCh := make(chan error, 1)
	go func() {
		defer close(ch)
		defer close(errCh)
		if _, err := os.Stat(dirpath); errors.Is(err, os.ErrNotExist) {
			return
		}
		if err := filepath.Walk(dirpath, func(path string, info fs.FileInfo, err error) error {
			if err != nil {
				return gerrors.Wrap(err)
			}
			if dirpath == path { // not interested in parent directory itself
				return nil
			}
			fullKey, err := filepath.Rel(s.basepath, path)
			if err != nil {
				return gerrors.Wrap(err)
			}
			// is it working with real paths? and trailing slash?
			if !strings.HasPrefix(fullKey, prefix) {
				if info.IsDir() {
					return filepath.SkipDir
				}
				return nil
			}
			if info.IsDir() {
				return nil
			}

			symlink := ""
			if info.Mode()&os.ModeSymlink == os.ModeSymlink {
				symlink, err = os.Readlink(path)
				if err != nil {
					return gerrors.Wrap(err)
				}
			}
			select {
			case <-ctx.Done():
				return gerrors.New("context was canceled")
			case ch <- &base.StorageObject{
				Key:     strings.TrimPrefix(filepath.ToSlash(fullKey), prefix),
				Size:    info.Size(),
				ModTime: info.ModTime(),
				Symlink: symlink,
			}:
			}
			return nil
		}); err != nil {
			errCh <- gerrors.Wrap(err)
			return
		}
	}()
	return ch, errCh
}
