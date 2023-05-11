package gcp

import (
	"bytes"
	"context"
	"errors"
	"io"
	"io/fs"
	"os"
	"path"
	"path/filepath"
	"strings"
	"time"

	"github.com/dstackai/dstack/runner/internal/backend/base"
	"github.com/dstackai/dstack/runner/internal/common"
	"go.uber.org/atomic"

	"cloud.google.com/go/storage"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"google.golang.org/api/iterator"
)

var ErrTagNotFound = errors.New("tag not found")

type GCPStorage struct {
	client     *storage.Client
	bucket     *storage.BucketHandle
	project    string
	bucketName string
}

type FileInfo struct {
	Size     int64
	Modified time.Time
}

func NewGCPStorage(project, bucketName string) (*GCPStorage, error) {
	ctx := context.TODO()
	client, err := storage.NewClient(ctx)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	bucket := client.Bucket(bucketName)
	if bucket == nil {
		return nil, gerrors.New("Cannot access bucket")
	}
	return &GCPStorage{
		client:     client,
		bucket:     bucket,
		project:    project,
		bucketName: bucketName,
	}, nil
}

func (gstorage *GCPStorage) GetFile(ctx context.Context, key string) ([]byte, error) {
	obj := gstorage.bucket.Object(key)
	reader, err := obj.NewReader(ctx)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	defer reader.Close()
	buffer := new(bytes.Buffer)
	_, err = io.Copy(buffer, reader)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return buffer.Bytes(), nil
}

func (gstorage *GCPStorage) PutFile(ctx context.Context, key string, contents []byte) error {
	obj := gstorage.bucket.Object(key)
	writer := obj.NewWriter(ctx)
	reader := bytes.NewReader(contents)
	_, err := io.Copy(writer, reader)
	if err != nil {
		return gerrors.Wrap(err)
	}
	return writer.Close()
}

func (gstorage *GCPStorage) ListFile(ctx context.Context, prefix string) ([]string, error) {
	query := &storage.Query{Prefix: prefix}
	names := make([]string, 0)
	it := gstorage.bucket.Objects(ctx, query)
	for {
		attrs, err := it.Next()
		if err == iterator.Done {
			break
		}
		if err != nil {
			return nil, gerrors.Wrap(err)
		}
		names = append(names, attrs.Name)
	}
	return names, nil
}

func (gstorage *GCPStorage) DeleteFile(ctx context.Context, key string) error {
	obj := gstorage.bucket.Object(key)
	err := obj.Delete(ctx)
	return gerrors.Wrap(err)
}

func (gstorage *GCPStorage) RenameFile(ctx context.Context, oldKey, newKey string) error {
	if newKey == oldKey {
		return nil
	}
	src := gstorage.bucket.Object(oldKey)
	dst := gstorage.bucket.Object(newKey)
	copier := dst.CopierFrom(src)
	_, err := copier.Run(ctx)
	if err != nil {
		return gerrors.Wrap(err)
	}
	err = src.Delete(ctx)
	return gerrors.Wrap(err)
}

func (gstorage *GCPStorage) GetMetadata(ctx context.Context, key, tag string) (string, error) {
	obj := gstorage.bucket.Object(key)
	attrs, err := obj.Attrs(ctx)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	if value, ok := attrs.Metadata[tag]; ok {
		return value, nil
	}
	return "", gerrors.Wrap(ErrTagNotFound)
}

func (gstorage *GCPStorage) UploadDir(ctx context.Context, src, dst string) error {
	semaphore := make(base.Semaphore, base.TransferThreads)
	errorFound := atomic.NewBool(false)
	for file := range walkFiles(ctx, src) {
		key := path.Join(dst, strings.TrimPrefix(file, src))
		semaphore.Acquire(1)
		go func(file, key string) {
			defer semaphore.Release(1)
			if err := gstorage.uploadFile(ctx, file, key); err != nil {
				errorFound.Store(true)
				log.Error(ctx, "Failed to upload file", "Key", key, "err", err)
			}
		}(file, key)
	}
	semaphore.Acquire(base.TransferThreads) // gather
	if errorFound.Load() {
		return errors.New("upload: error occurred")
	}
	return nil
}

func (gstorage *GCPStorage) DownloadDir(ctx context.Context, src, dst string) error {
	semaphore := make(base.Semaphore, base.TransferThreads)
	errorFound := atomic.NewBool(false)
	query := &storage.Query{Prefix: src}
	it := gstorage.bucket.Objects(ctx, query)
	for {
		attrs, err := it.Next()
		if err == iterator.Done {
			break
		}
		if err != nil {
			return gerrors.Wrap(err)
		}
		dstFilepath := path.Join(dst, strings.TrimPrefix(attrs.Name, src))
		semaphore.Acquire(1)
		go func() {
			defer semaphore.Release(1)
			if err := gstorage.downloadFile(ctx, attrs.Name, dstFilepath); err != nil {
				errorFound.Store(true)
				log.Error(ctx, "Failed to download file", "Key", attrs.Name, "err", err)
			}
			if err := os.Chtimes(dstFilepath, attrs.Updated, attrs.Updated); err != nil {
				errorFound.Store(true)
				log.Error(ctx, "Failed to chtimes", "Path", dstFilepath, "err", err)
			}
		}()
	}
	semaphore.Acquire(base.TransferThreads)
	if errorFound.Load() {
		return errors.New("download: error occurred")
	}
	return nil
}

func (gstorage *GCPStorage) SyncDirUpload(ctx context.Context, srcDir, dstPrefix string) error {
	srcDir = common.AddTrailingSlash(srcDir)
	dstPrefix = common.AddTrailingSlash(dstPrefix)

	dstObjects := make(chan base.ObjectInfo)
	go func() {
		defer close(dstObjects)
		query := &storage.Query{Prefix: dstPrefix}
		it := gstorage.bucket.Objects(ctx, query)
		for {
			attrs, err := it.Next()
			if err == iterator.Done {
				break
			}
			if err != nil {
				log.Error(ctx, "Iterating objects", "prefix", dstPrefix, "err", err)
				return
			}
			dstObjects <- base.ObjectInfo{
				Key: strings.TrimPrefix(attrs.Name, dstPrefix),
				FileInfo: base.FileInfo{
					Size:     attrs.Size,
					Modified: attrs.Updated,
				},
			}
		}
	}()
	err := base.SyncDirUpload(
		ctx, srcDir, dstObjects,
		func(ctx context.Context, key string, _ base.FileInfo) error {
			/* delete object */
			key = path.Join(dstPrefix, key)
			return gstorage.DeleteFile(ctx, key)
		},
		func(ctx context.Context, key string, _ base.FileInfo) error {
			/* upload object */
			file := path.Join(srcDir, key)
			key = path.Join(dstPrefix, key)
			return gstorage.uploadFile(ctx, file, key)
		},
	)
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func walkFiles(ctx context.Context, local string) chan string {
	files := make(chan string)
	go func() {
		defer close(files)
		err := filepath.Walk(local, func(path string, info fs.FileInfo, err error) error {
			if err != nil {
				return err
			}
			files <- path
			return nil
		})
		if err != nil {
			log.Error(ctx, "Error while walking files", "err", err)
		}
	}()
	return files
}

func (gstorage *GCPStorage) uploadFile(ctx context.Context, src, dst string) error {
	f, err := os.Open(src)
	if err != nil {
		return gerrors.Wrap(err)
	}
	fileInfo, err := f.Stat()
	if err != nil {
		return gerrors.Wrap(err)
	}
	if fileInfo.IsDir() {
		return nil
	}
	obj := gstorage.bucket.Object(dst)
	writer := obj.NewWriter(ctx)
	_, err = io.Copy(writer, f)
	if err != nil {
		return gerrors.Wrap(err)
	}
	return writer.Close()
}

func (gstorage *GCPStorage) downloadFile(ctx context.Context, src, dst string) error {
	os.MkdirAll(filepath.Dir(dst), 0o755)
	obj := gstorage.bucket.Object(src)
	reader, err := obj.NewReader(ctx)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer reader.Close()
	file, err := os.Create(dst)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer file.Close()
	_, err = io.Copy(file, reader)
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}
