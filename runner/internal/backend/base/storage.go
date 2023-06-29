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

type StorageLister func(ctx context.Context, src string) (<-chan *StorageObject, <-chan error)
type FileUploader func(ctx context.Context, storage Storage, src, key string) error

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

// UploadDir implements both: coping files from the local file system to the storage
// and optimally synchronizing file trees based on size and modify date.
// UploadDir keeps relative symlinks bounded by the src directory as symlinks.
// Set delete=true to remove remote objects not presented locally.
// Set withoutChanges=true to upload all local files without testing for changes.
func UploadDir(ctx context.Context, storage Storage, src, key string, delete, withoutChanges bool) error {
	// dependency injection for testing
	return UploadDirMocked(ctx, storage, src, key, delete, withoutChanges, ListFiles, UploadFile)
}

func UploadDirMocked(ctx context.Context, storage Storage, src, key string, delete, withoutChanges bool, srcLister StorageLister, fileUploader FileUploader) error {
	src = common.AddTrailingSlash(src)
	key = common.AddTrailingSlash(key)

	stat := struct{ Delete, NotChanged, Upload int }{}
	uploadQueue := make([]StorageObject, 0)

	objects, objectsErr := storage.List(ctx, key)
	files, filesErr := srcLister(ctx, src)

	// Match two sorted lists: objects (remote) and files (local)
	// 1. If the item only exists in objects — delete object
	//      delete=false prohibit deletion
	// 2. If the item only exists in files — upload file
	// 3. If the item exists in both lists — compare and upload file
	//      withoutChanges=true always upload
	obj, err := objectsListPop(objects, objectsErr)
	if err != nil {
		return gerrors.Wrap(err)
	}
	file, err := objectsListPop(files, filesErr)
	if err != nil {
		return gerrors.Wrap(err)
	}
	for obj != nil || file != nil {
		// 1. Iterate outdated objects
		for obj != nil {
			if file == nil || obj.Key < file.Key {
				if delete {
					stat.Delete++
					if err := storage.Delete(ctx, path.Join(key, obj.Key)); err != nil {
						return gerrors.Wrap(err)
					}
				}
			} else {
				break
			}
			obj, err = objectsListPop(objects, objectsErr)
			if err != nil {
				return gerrors.Wrap(err)
			}
		}
		// 3. A match
		if obj != nil && file != nil && file.Key == obj.Key {
			if withoutChanges || !obj.Equals(*file) {
				stat.Upload++
				uploadQueue = append(uploadQueue, *file)
			} else {
				stat.NotChanged++
			}
			obj, err = objectsListPop(objects, objectsErr)
			if err != nil {
				return gerrors.Wrap(err)
			}
			file, err = objectsListPop(files, filesErr)
			if err != nil {
				return gerrors.Wrap(err)
			}
		}
		// 2. Iterate new files
		for file != nil {
			if obj == nil || obj.Key > file.Key {
				stat.Upload++
				uploadQueue = append(uploadQueue, *file)
			} else {
				break
			}
			file, err = objectsListPop(files, filesErr)
			if err != nil {
				return gerrors.Wrap(err)
			}
		}
	}

	log.Trace(ctx, "UploadDir stats", "delete", stat.Delete, "not-changed", stat.NotChanged, "upload", stat.Upload, "src", src, "key", key)
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
				if err := fileUploader(ctx, storage, filePath, objKey); err != nil {
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

func ListFiles(ctx context.Context, src string) (<-chan *StorageObject, <-chan error) {
	ch := make(chan *StorageObject)
	errCh := make(chan error, 1)
	go func() {
		defer close(ch)
		defer close(errCh)
		if err := filepath.Walk(src, func(path string, info fs.FileInfo, err error) error {
			if err != nil {
				return gerrors.Wrap(err)
			}
			if info.IsDir() {
				return nil
			}
			key, err := filepath.Rel(src, path)
			if err != nil {
				return gerrors.Wrap(err)
			}
			symlink := ""
			if info.Mode()&os.ModeSymlink == os.ModeSymlink {
				symlink, err = os.Readlink(path)
				if err != nil {
					return gerrors.Wrap(err)
				}
				rel, err := filepath.Rel(src, filepath.Join(filepath.Dir(path), symlink))
				if err != nil || filepath.IsAbs(symlink) || rel == ".." || strings.HasPrefix(rel, "../") {
					// upload target file if the symlink points outside the tree
					symlink = ""
				}
			}
			select {
			case <-ctx.Done():
				return gerrors.New("context was canceled")
			case ch <- &StorageObject{
				Key:     filepath.ToSlash(key),
				Size:    info.Size(),
				ModTime: info.ModTime(),
				Symlink: symlink,
			}:
			}
			return nil
		}); err != nil {
			errCh <- err
		}
	}()
	return ch, errCh
}

func objectsListPop(ch <-chan *StorageObject, errCh <-chan error) (obj *StorageObject, err error) {
	obj = <-ch
	if obj == nil {
		err = gerrors.Wrap(<-errCh)
	}
	return
}
