package gcp

import (
	"bytes"
	"context"
	"errors"
	"io"

	"cloud.google.com/go/storage"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"google.golang.org/api/iterator"
)

var ErrTagNotFound = errors.New("tag not found")

type GCPStorage struct {
	client     *storage.Client
	bucket     *storage.BucketHandle
	project    string
	bucketName string
}

func NewGCPStorage(project, bucketName string) (*GCPStorage, error) {
	ctx := context.TODO()
	client, _ := storage.NewClient(ctx)
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
	io.Copy(buffer, reader)
	return buffer.Bytes(), nil
}

func (gstorage *GCPStorage) PutFile(ctx context.Context, key string, contents []byte) error {
	obj := gstorage.bucket.Object(key)
	writer := obj.NewWriter(ctx)
	reader := bytes.NewReader(contents)
	io.Copy(writer, reader)
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
