package local

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
)

var ErrTagNotFound = errors.New("tag not found")

type ClientS3 struct {
	cli *s3.Client
}

func NewClientS3(region string) *ClientS3 {
	c := new(ClientS3)
	ctx := context.TODO()
	cfg, err := config.LoadDefaultConfig(
		ctx,
		config.WithRegion(region),
	)
	if err != nil {
		return nil
	}
	c.cli = s3.NewFromConfig(cfg)
	return c
}

func (c *ClientS3) GetFile(ctx context.Context, bucket, key string) ([]byte, error) {
	out, err := c.cli.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	defer func() {
		err = out.Body.Close()
		if err != nil {
			log.Error(ctx, "Fail close body", "err", err)
		}
	}()

	buffer := new(bytes.Buffer)
	size, err := io.Copy(buffer, out.Body)
	if size != out.ContentLength {
		return nil, gerrors.New("size not equal")
	}
	return buffer.Bytes(), nil
}

func (c *ClientS3) PutFile(ctx context.Context, bucket, key string, file []byte) error {
	_, err := c.cli.PutObject(ctx, &s3.PutObjectInput{
		Bucket:        aws.String(bucket),
		Key:           aws.String(key),
		Body:          bytes.NewReader(file),
		ContentLength: int64(len(file)),
	})
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (c *ClientS3) RenameFile(ctx context.Context, bucket, oldKey, newKey string) error {
	if oldKey == newKey {
		return nil
	}
	_, err := c.cli.CopyObject(ctx, &s3.CopyObjectInput{
		Bucket:     aws.String(bucket),
		CopySource: aws.String(fmt.Sprintf("%s/%s", bucket, oldKey)),
		Key:        aws.String(newKey),
	})
	if err != nil {
		return gerrors.Wrap(err)
	}
	_, err = c.cli.DeleteObject(ctx, &s3.DeleteObjectInput{
		Bucket: aws.String(bucket),
		Key:    aws.String(oldKey),
	})
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (c *ClientS3) ListFile(ctx context.Context, bucket, prefix string) ([]string, error) {
	resp := make([]string, 0)
	pager := s3.NewListObjectsV2Paginator(c.cli, &s3.ListObjectsV2Input{
		Bucket: aws.String(bucket),
		Prefix: aws.String(prefix),
	})
	for pager.HasMorePages() {
		page, err := pager.NextPage(ctx)
		if err != nil {
			return nil, gerrors.Wrap(err)
		}
		for _, file := range page.Contents {
			key := aws.ToString(file.Key)
			if strings.HasSuffix(key, "/") {
				continue
			}
			resp = append(resp, key)
		}
	}
	return resp, nil
}

func (c *ClientS3) ListDir(ctx context.Context, bucket, prefix string) ([]string, error) {
	resp := make([]string, 0)
	pager := s3.NewListObjectsV2Paginator(c.cli, &s3.ListObjectsV2Input{
		Bucket: aws.String(bucket),
		Prefix: aws.String(prefix),
	})
	for pager.HasMorePages() {
		page, err := pager.NextPage(ctx)
		if err != nil {
			return nil, gerrors.Wrap(err)
		}
		for _, file := range page.Contents {
			key := aws.ToString(file.Key)
			resp = append(resp, key)
		}
	}
	return resp, nil
}

func (c *ClientS3) DeleteFile(ctx context.Context, bucket, key string) error {
	_, err := c.cli.DeleteObject(ctx, &s3.DeleteObjectInput{
		Bucket: aws.String(bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (c *ClientS3) MetadataFile(ctx context.Context, bucket, key, tag string) (string, error) {
	out, err := c.cli.HeadObject(ctx, &s3.HeadObjectInput{
		Bucket: aws.String(bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	if value, ok := out.Metadata[tag]; ok {
		return value, nil
	}
	return "", gerrors.Wrap(ErrTagNotFound)
}
