package gcp

import (
	"context"
	"errors"
	"github.com/dstackai/dstack/runner/internal/backend/base"
	"io"
	"strings"

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

func (s *GCPStorage) Download(ctx context.Context, key string, writer io.Writer) error {
	obj := s.bucket.Object(key)
	reader, err := obj.NewReader(ctx)
	if err != nil {
		return gerrors.Wrap(err)
	}
	_, err = io.Copy(writer, reader)
	return gerrors.Wrap(err)
}

func (s *GCPStorage) Upload(ctx context.Context, reader io.Reader, key string) error {
	obj := s.bucket.Object(key)
	writer := obj.NewWriter(ctx)
	_, err := io.Copy(writer, reader)
	if err != nil {
		return gerrors.Wrap(err)
	}
	return gerrors.Wrap(writer.Close())
}

func (s *GCPStorage) Delete(ctx context.Context, key string) error {
	obj := s.bucket.Object(key)
	return gerrors.Wrap(obj.Delete(ctx))
}

func (s *GCPStorage) Rename(ctx context.Context, oldKey, newKey string) error {
	if newKey == oldKey {
		return nil
	}
	src := s.bucket.Object(oldKey)
	dst := s.bucket.Object(newKey)
	copier := dst.CopierFrom(src)
	_, err := copier.Run(ctx)
	if err != nil {
		return gerrors.Wrap(err)
	}
	return gerrors.Wrap(src.Delete(ctx))
}

func (s *GCPStorage) CreateSymlink(ctx context.Context, key, symlink string) error {
	obj := s.bucket.Object(key)
	writer := obj.NewWriter(ctx)
	writer.Metadata = map[string]string{
		"symlink": symlink,
	}
	return gerrors.Wrap(writer.Close())
}

func (s *GCPStorage) List(ctx context.Context, prefix string) (<-chan *base.StorageObject, <-chan error) {
	it := s.bucket.Objects(ctx, &storage.Query{Prefix: prefix})
	ch := make(chan *base.StorageObject)
	errCh := make(chan error, 1)
	go func() {
		defer close(ch)
		defer close(errCh)
		for {
			attrs, err := it.Next()
			if err == iterator.Done {
				break
			} else if err != nil {
				errCh <- gerrors.Wrap(err)
				return
			}
			symlink, ok := attrs.Metadata["symlink"]
			if !ok {
				symlink = ""
			}
			ch <- &base.StorageObject{
				Key:     strings.TrimPrefix(attrs.Name, prefix),
				Size:    attrs.Size,
				ModTime: attrs.Updated,
				Symlink: symlink,
			}
		}
	}()
	return ch, errCh
}

func (s *GCPStorage) GetMetadata(ctx context.Context, key, tag string) (string, error) {
	obj := s.bucket.Object(key)
	attrs, err := obj.Attrs(ctx)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	if value, ok := attrs.Metadata[tag]; ok {
		return value, nil
	}
	return "", gerrors.Wrap(ErrTagNotFound)
}
