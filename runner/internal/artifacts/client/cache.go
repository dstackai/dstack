package client

import (
	"context"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"mime"
	"os"
	"path"
	"path/filepath"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/s3/manager"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/smithy-go"
	"github.com/dstackai/dstackai/runner/consts"
	"github.com/dstackai/dstackai/runner/internal/gerrors"
	"github.com/dstackai/dstackai/runner/internal/log"
	"go.uber.org/atomic"
)

const MAX_THREADS = 10
const MIN_SIZE = 5 * 1024 * 1024

type ObjectType struct {
	mode os.FileMode
}

func (o ObjectType) String() string {
	switch mode := o.mode; {
	case mode.IsRegular():
		return "file"
	case mode.IsDir():
		return "directory"
	case mode&os.ModeSymlink != 0:
		return "symlink"
	}
	return ""
}

func (o ObjectType) IsDir() bool {
	return o.mode.IsDir()
}

func (o ObjectType) IsSymlink() bool {
	return o.mode&os.ModeSymlink != 0
}

type Object struct {
	Key     string     `json:"key,omitempty"`
	Etag    string     `json:"etag,omitempty"`
	ModTime *time.Time `json:"last_modified,omitempty"`
	Type    ObjectType `json:"mode,omitempty"`
	Size    int64      `json:"size,omitempty"`
	Err     error      `json:"error,omitempty"`
}

type fileJob struct {
	path string
	info os.FileInfo
}

type ProgressBar struct {
	totalSize   atomic.Int64
	currentSize atomic.Int64
	totalFile   atomic.Int64
	currentFile atomic.Int64
	averageSize atomic.Int64
}

type Copier struct {
	cli        *s3.Client
	downloader *manager.Downloader
	uploader   *manager.Uploader
	threads    semaphore
	pb         *ProgressBar
}

func New(region string) *Copier {
	c := new(Copier)
	ctx := context.TODO()
	cfg, err := config.LoadDefaultConfig(
		ctx,
		config.WithRegion(region),
	)
	if err != nil {
		return nil
	}
	c.cli = s3.NewFromConfig(cfg)
	c.downloader = manager.NewDownloader(c.cli)
	c.uploader = manager.NewUploader(c.cli)

	c.threads = make(semaphore, MAX_THREADS)
	c.pb = &ProgressBar{
		totalSize:   atomic.Int64{},
		currentSize: atomic.Int64{},
		totalFile:   atomic.Int64{},
		currentFile: atomic.Int64{},
		averageSize: atomic.Int64{},
	}
	return c
}

func (pb *ProgressBar) reset() {
	pb.totalSize = atomic.Int64{}
	pb.currentSize = atomic.Int64{}
	pb.totalFile = atomic.Int64{}
	pb.currentFile = atomic.Int64{}
	pb.averageSize = atomic.Int64{}
}
func (pb *ProgressBar) average() {
	r := pb.totalFile.Load()
	if r != 0 {
		pb.averageSize.Store(pb.totalSize.Load() / r)
	}
}
func (pb *ProgressBar) size() int64 {
	if pb.averageSize.Load() <= MIN_SIZE {
		return MIN_SIZE
	}
	return pb.averageSize.Load()
}

func (c *Copier) incTotalSize(fileSize int64) {
	c.pb.totalSize.Add(fileSize)
	c.pb.totalFile.Inc()
}

func (c *Copier) updateBars(downloadSize int64) {
	c.pb.currentSize.Add(downloadSize)
	c.pb.currentFile.Inc()
}

func (c *Copier) statDownload(bucket, remote string) {
	c.pb.reset()
	for file := range c.listObjects(bucket, remote) {
		c.incTotalSize(file.Size)
	}
	c.pb.average()
}
func (c *Copier) statUpload(local string) {
	c.pb.reset()
	err := filepath.Walk(local, func(file string, info fs.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if !info.IsDir() {
			c.incTotalSize(info.Size())
		}
		return nil
	})
	if err != nil {

	}
	c.pb.average()
}

func (c *Copier) listObjects(bucket, remote string) <-chan *Object {
	listInput := s3.ListObjectsV2Input{
		Bucket: &bucket,
		Prefix: &remote,
	}
	objCh := make(chan *Object)
	go func() {
		defer close(objCh)
		pager := s3.NewListObjectsV2Paginator(c.cli, &listInput)
		for pager.HasMorePages() {
			page, err := pager.NextPage(context.Background())
			if err != nil {
				objCh <- &Object{Err: err}
				return
			}
			for _, file := range page.Contents {
				key := aws.StringValue(file.Key)
				etag := aws.StringValue(file.ETag)
				mod := aws.TimeValue(file.LastModified).UTC()
				var objType os.FileMode
				if strings.HasSuffix(key, "/") {
					objType = os.ModeDir
				}
				objCh <- &Object{
					Key:     key,
					Etag:    strings.Trim(etag, `"`),
					ModTime: &mod,
					Type:    ObjectType{objType},
					Size:    file.Size,
				}
			}
		}
	}()
	return objCh
}
func (c *Copier) CreateDirObject(ctx context.Context, bucket, path string) error {
	if len(path) < 1 || path == "/" {
		return gerrors.New("dir object need not be created for root path")
	}
	if path[len(path)-1] != '/' {
		path += "/"
	}
	_, err := c.cli.HeadObject(ctx, &s3.HeadObjectInput{
		Key:    &path,
		Bucket: &bucket,
	})
	var ae smithy.APIError
	if errors.As(err, &ae) && ae.ErrorCode() == "NotFound" {
		log.Info(ctx, "Creating object to indicate directory", "bucket", bucket, "path", path)
		_, err = c.cli.PutObject(ctx, &s3.PutObjectInput{
			Bucket: &bucket,
			Key:    &path,
		})
		if err != nil {
			return gerrors.Wrap(err)
		}
		return nil
	}
	return gerrors.Wrap(err)
}

func (c *Copier) Download(ctx context.Context, bucket, remote, local string) {
	//Check local file cache
	if _, err := os.Stat(filepath.Join(local, consts.FILE_LOCK_FULL_DOWNLOAD)); err == nil {
		return
	}
	c.statDownload(bucket, remote)
	errorFound := atomic.NewBool(false)
	for file := range c.listObjects(bucket, remote) {
		if file.Err != nil {
			log.Error(ctx, "List files", "err", file.Err)
			errorFound.Store(true)
			continue
		}
		c.threads.acquire(1)
		go func(file *Object) {
			defer c.threads.release(1)
			theFilePath := strings.TrimPrefix(file.Key, remote)
			theFilePath = filepath.Join(local, theFilePath)
			if file.Type.IsDir() {
				log.Trace(ctx, "Make dir", "dir", theFilePath)
				if err := os.MkdirAll(theFilePath, 0755); err != nil {
					log.Error(ctx, "Create dir", "err", err)
					errorFound.Store(true)
				}
				return
			}
			if err := os.MkdirAll(path.Dir(theFilePath), 0755); err != nil {
				return
			}
			if _, err := os.Stat(theFilePath); err == nil {
				// file exists
				return
			}
			theFile, err := os.OpenFile(theFilePath, os.O_RDWR|os.O_CREATE|os.O_TRUNC, 0777)
			if err != nil {
				log.Error(ctx, "Create file", "err", err)
				errorFound.Store(true)
				return
			}
			defer func() {
				err = theFile.Close()
				if err != nil {
					log.Error(ctx, "Close file", "err", err)
					errorFound.Store(true)
				}
			}()
			log.Trace(ctx, "Download file", "path", theFilePath)
			var size int64
			if file.Size < c.pb.size() {
				size, err = c.doDownload(ctx, bucket, file.Key, theFile, 1, MIN_SIZE)
			} else {
				size, err = c.doDownload(ctx, bucket, file.Key, theFile, file.Size/c.pb.size(), c.pb.size())
			}
			if size != file.Size {
				log.Info(ctx, "The file size is not equal source", "size", size/file.Size)
			}
			if err != nil {
				log.Error(ctx, "Download file", "err", err)
				errorFound.Store(true)
				return
			}
			c.updateBars(file.Size)
			return
		}(file)
	}
	c.threads.acquire(MAX_THREADS)
	if !errorFound.Load() {
		log.Info(ctx, "Lock directory")
		theFile, err := os.Create(filepath.Join(local, consts.FILE_LOCK_FULL_DOWNLOAD))
		if err != nil {
			log.Error(ctx, "Create lock file", "err", err)
			return
		}
		defer func() {
			err = theFile.Close()
			if err != nil {
				log.Error(ctx, "Close lock file", "err", err)
			}
		}()
	}
}
func (c *Copier) Upload(ctx context.Context, bucket, remote, local string) {
	c.statUpload(local)
	errorFound := atomic.NewBool(false)
	for file := range walkFiles(local) {
		c.threads.acquire(1)
		go func(file *fileJob) {
			defer c.threads.release(1)
			key := path.Join(remote, strings.TrimPrefix(file.path, local))
			if file.info.IsDir() {
				log.Trace(ctx, "Create dir", "dir", key)
				err := c.CreateDirObject(ctx, bucket, key)
				if err != nil {
					log.Error(ctx, "Create dir in s3", "err", err)
				}
				return
			}
			theFile, err := os.Open(file.path)
			if err != nil {
				log.Error(ctx, "Open file", "err", err)
				errorFound.Store(true)
				return
			}
			log.Trace(ctx, "Upload file", "path", file.path)
			mimeType := mime.TypeByExtension(path.Ext(file.path))
			if mimeType == "" {
				mimeType = "binary/octet-stream"
			}
			if file.info.Size() < c.pb.size() {
				err = c.doUpload(ctx, bucket, key, theFile, mimeType, 1, MIN_SIZE)
			} else {
				err = c.doUpload(ctx, bucket, key, theFile, mimeType, int(file.info.Size()/c.pb.size()), c.pb.size())
			}
			if err != nil {
				log.Error(ctx, "Upload file", "err", err)
				errorFound.Store(true)
				return
			}
			c.updateBars(file.info.Size())
			return
		}(file)
	}
	c.threads.acquire(MAX_THREADS)
	if !errorFound.Load() {
		log.Info(ctx, "Lock directory")
		theFile, err := os.Create(filepath.Join(local, consts.FILE_LOCK_FULL_DOWNLOAD))
		if err != nil {
			log.Error(ctx, "Create lock file", "err", err)
			return
		}
		defer func() {
			err = theFile.Close()
			if err != nil {
				log.Error(ctx, "Close lock file", "err", err)
			}
		}()
	}
}

func walkFiles(local string) chan *fileJob {
	files := make(chan *fileJob)
	go func() {
		defer close(files)
		err := filepath.Walk(local, func(path string, info fs.FileInfo, err error) error {
			if err != nil {
				return err
			}
			files <- &fileJob{
				path: path,
				info: info,
			}
			return nil
		})

		if err != nil {
			fmt.Println(err)
		}
	}()
	return files
}

func (c *Copier) doDownload(ctx context.Context, fromBucket, fromKey string, to io.WriterAt, concurrency int64, batchSize int64) (int64, error) {
	size, err := c.downloader.Download(ctx, to, &s3.GetObjectInput{
		Bucket: &fromBucket,
		Key:    &fromKey,
	}, func(d *manager.Downloader) {
		d.PartSize = batchSize
		d.Concurrency = int(concurrency) + 1
	})
	return size, err
}
func (c *Copier) doUpload(ctx context.Context, toBucket, toKey string, reader io.Reader, mimeType string, concurrency int, batchSize int64) error {
	if mimeType == "" {
		mimeType = "binary/octet-stream"
	}
	_, err := c.uploader.Upload(ctx, &s3.PutObjectInput{
		Bucket:      &toBucket,
		Key:         &toKey,
		Body:        reader,
		ContentType: &mimeType,
	}, func(u *manager.Uploader) {
		u.Concurrency = concurrency

		u.PartSize = batchSize
	})
	return err
}
