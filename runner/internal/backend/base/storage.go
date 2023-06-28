package base

import (
	"bufio"
	"bytes"
	"context"
	"github.com/dstackai/dstack/runner/internal/common"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"golang.org/x/sync/errgroup"
	"io"
	"io/fs"
	"os"
	"path"
	"path/filepath"
	"strings"
	"time"
)

type StorageObject struct {
	// Key is relative to the queried prefix
	Key     string
	Size    int64
	ModTime time.Time
	Symlink string
}

type Storage interface {
	Download(ctx context.Context, key string, writer io.Writer) error
	Upload(ctx context.Context, reader io.Reader, key string) error
	Delete(ctx context.Context, key string) error
	Rename(ctx context.Context, oldKey, newKey string) error
	CreateSymlink(ctx context.Context, key, symlink string) error
	GetMetadata(ctx context.Context, key, tag string) (string, error)
	// List generates StorageObject-s in lexicographical order
	List(ctx context.Context, prefix string) (<-chan *StorageObject, <-chan error)
}

func (a StorageObject) Equals(b StorageObject) bool {
	return a.Key == b.Key && a.Size == b.Size && a.ModTime == b.ModTime && a.Symlink == b.Symlink
}

func DownloadDir(ctx context.Context, storage Storage, key, dst string) error {
	key = common.AddTrailingSlash(key)
	dst = common.AddTrailingSlash(dst)
	objects, errCh := storage.List(ctx, key)

	g, ctx := errgroup.WithContext(ctx)
	g.SetLimit(TransferThreads)
	for rObj := range objects {
		obj := rObj // goroutines and range variables don't work together
		objKey := path.Join(key, obj.Key)
		filePath := filepath.Join(dst, obj.Key)
		g.Go(func() error {
			if err := os.MkdirAll(filepath.Dir(filePath), 0o755); err != nil {
				return gerrors.Wrap(err)
			}
			if obj.Size == 0 && obj.Symlink != "" {
				if err := os.Symlink(obj.Symlink, filePath); err != nil {
					return gerrors.Wrap(err)
				}
			} else {
				if err := DownloadFile(ctx, storage, objKey, filePath); err != nil {
					return gerrors.Wrap(err)
				}
				if err := os.Chtimes(filePath, obj.ModTime, obj.ModTime); err != nil {
					return gerrors.Wrap(err)
				}
			}
			return nil
		})
	}
	if err := g.Wait(); err != nil {
		return gerrors.Wrap(err)
	}
	select {
	case err := <-errCh:
		return gerrors.Wrap(err)
	default:
	}
	return nil
}

// UploadDir save local files tree to the Storage
// If delete is true — files existing only in storage would be deleted
// If withoutChanges is true — files would always be uploaded despite the same size and modification time
func UploadDir(ctx context.Context, storage Storage, src, key string, delete, withoutChanges bool) error {
	src = common.AddTrailingSlash(src)
	key = common.AddTrailingSlash(key)
	uploadQueue := make([]StorageObject, 0)
	objects, errCh := storage.List(ctx, key)
	statDelete := 0
	statNotChanged := 0
	if err := filepath.Walk(src, func(filePath string, info fs.FileInfo, err error) error {
		if err != nil {
			return gerrors.Wrap(err)
		}
		if info.IsDir() {
			return nil
		}
		fileKey, err := filepath.Rel(src, filePath)
		if err != nil {
			return gerrors.Wrap(err)
		}

		var obj *StorageObject
		for {
			select {
			case obj = <-objects:
			case err = <-errCh:
				if err != nil {
					return gerrors.Wrap(err)
				}
				break
			}
			if obj == nil || obj.Key >= fileKey {
				break
			}
			if delete {
				statDelete++
				if err := storage.Delete(ctx, path.Join(key, obj.Key)); err != nil {
					return gerrors.Wrap(err)
				}
			}
		}

		symlink := ""
		if info.Mode()&os.ModeSymlink == os.ModeSymlink {
			symlink, err = os.Readlink(filePath)
			if err != nil {
				return gerrors.Wrap(err)
			}
			rel, err := filepath.Rel(src, filepath.Join(filepath.Dir(filePath), symlink))
			if err != nil || filepath.IsAbs(symlink) || rel == ".." || strings.HasPrefix(rel, "../") {
				// upload target file if the symlink points outside the tree
				symlink = ""
			}
		}
		file := StorageObject{
			Key:     fileKey,
			Size:    info.Size(),
			ModTime: info.ModTime(),
			Symlink: symlink,
		}

		if obj == nil || withoutChanges || !obj.Equals(file) {
			uploadQueue = append(uploadQueue, file)
		} else {
			statNotChanged++
		}
		return nil
	}); err != nil {
		return gerrors.Wrap(err)
	}

	log.Trace(ctx, "UploadDir stats", "delete", statDelete, "not-changed", statNotChanged, "upload", len(uploadQueue), "src", src, "key", key)
	g, ctx := errgroup.WithContext(ctx)
	g.SetLimit(TransferThreads)
	for _, rFile := range uploadQueue {
		file := rFile // goroutines and range variables don't work together
		g.Go(func() error {
			objKey := path.Join(key, file.Key)
			filePath := filepath.Join(src, file.Key)
			if file.Symlink != "" {
				if err := storage.CreateSymlink(ctx, objKey, file.Symlink); err != nil {
					return gerrors.Wrap(err)
				}
			} else {
				if err := UploadFile(ctx, storage, filePath, objKey); err != nil {
					return gerrors.Wrap(err)
				}
			}
			return nil
		})
	}
	if err := g.Wait(); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func DownloadFile(ctx context.Context, storage Storage, key, dst string) error {
	file, err := os.Create(dst)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = file.Close() }()
	if err := storage.Download(ctx, key, file); err != nil {
		_ = os.Remove(dst)
		return gerrors.Wrap(err)
	}
	return nil
}

func UploadFile(ctx context.Context, storage Storage, src, key string) error {
	file, err := os.Open(src)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = file.Close() }()
	if err := storage.Upload(ctx, file, key); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func GetObject(ctx context.Context, storage Storage, key string) ([]byte, error) {
	var b bytes.Buffer
	w := bufio.NewWriter(&b)
	if err := storage.Download(ctx, key, w); err != nil {
		return nil, gerrors.Wrap(err)
	}
	return b.Bytes(), nil
}

func PutObject(ctx context.Context, storage Storage, key string, data []byte) error {
	r := bytes.NewReader(data)
	if err := storage.Upload(ctx, r, key); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func ListObjects(ctx context.Context, storage Storage, prefix string) ([]string, error) {
	list := make([]string, 0)
	objects, errCh := storage.List(ctx, prefix)
	for obj := range objects {
		list = append(list, prefix+obj.Key)
	}
	select {
	case err := <-errCh:
		if err != nil {
			return nil, gerrors.Wrap(err)
		}
	default:
	}
	return list, nil
}
