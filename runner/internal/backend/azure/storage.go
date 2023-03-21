package azure

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path"
	"path/filepath"
	"strings"

	"github.com/Azure/azure-sdk-for-go/sdk/azcore"
	"github.com/Azure/azure-sdk-for-go/sdk/storage/azblob"
	"github.com/Azure/azure-sdk-for-go/sdk/storage/azblob/container"
	"github.com/dstackai/dstack/runner/internal/gerrors"
)

var ErrTagNotFound = errors.New("tag not found")

type AzureStorage struct {
	storageClient   *azblob.Client
	containerClient *container.Client
	container       string
}

func NewAzureStorage(credential azcore.TokenCredential, url string, container string) (*AzureStorage, error) {
	storageClient, err := azblob.NewClient(url, credential, nil)
	if err != nil {
		fmt.Printf("Initialization blob service failure: %+v", err)
		return nil, err
	}
	containerClient := storageClient.ServiceClient().NewContainerClient(container)
	return &AzureStorage{
		storageClient:   storageClient,
		containerClient: containerClient,
		container:       container,
	}, nil
}

func (azstorage AzureStorage) GetFile(ctx context.Context, key string) ([]byte, error) {
	contents := bytes.Buffer{}
	get, err := azstorage.containerClient.NewBlobClient(key).DownloadStream(ctx, nil)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	retryReader := get.NewRetryReader(ctx, &azblob.RetryReaderOptions{})
	_, err = contents.ReadFrom(retryReader)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return contents.Bytes(), nil
}

func (azstorage AzureStorage) PutFile(ctx context.Context, key string, contents []byte) error {
	_, err := azstorage.storageClient.UploadBuffer(ctx, azstorage.container, key, contents, nil)
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (azstorage AzureStorage) ListFile(ctx context.Context, prefix string) ([]string, error) {
	pager := azstorage.containerClient.NewListBlobsFlatPager(&azblob.ListBlobsFlatOptions{Prefix: &prefix})
	var result []string
	for pager.More() {
		resp, err := pager.NextPage(ctx)
		if err != nil {
			return nil, gerrors.Wrap(err)
		}
		for _, blob := range resp.Segment.BlobItems {
			result = append(result, strings.Clone(*blob.Name))
		}
	}
	return result, nil
}

func (azstorage AzureStorage) RenameFile(ctx context.Context, oldKey, newKey string) error {
	if oldKey == newKey {
		return nil
	}
	source := azstorage.containerClient.NewBlobClient(oldKey)
	_, err := azstorage.containerClient.NewBlobClient(newKey).CopyFromURL(ctx, source.URL(), nil)
	if err != nil {
		return gerrors.Wrap(err)
	}
	_, err = source.Delete(ctx, nil)
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (azstorage AzureStorage) GetMetadata(ctx context.Context, key string, tag string) (string, error) {
	properties, err := azstorage.containerClient.NewBlobClient(key).GetProperties(ctx, nil)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	if value, ok := properties.Metadata[tag]; ok {
		return strings.Clone(*value), nil
	}
	return "", gerrors.Wrap(ErrTagNotFound)
}

func (azstorage AzureStorage) DownloadDir(ctx context.Context, src, dst string) error {
	files, err := azstorage.ListFile(ctx, src)
	if err != nil {
		return gerrors.Wrap(err)
	}
	for _, file := range files {
		dstFilepath := path.Join(dst, strings.TrimPrefix(file, src))
		os.MkdirAll(filepath.Dir(dstFilepath), 0o755)
		err = func() error {
			dstFile, err := os.Create(dstFilepath)
			if err != nil {
				return gerrors.Wrap(err)
			}
			defer dstFile.Close()
			_, err = azstorage.containerClient.NewBlobClient(file).DownloadFile(ctx, dstFile, nil)
			if err != nil {
				return gerrors.Wrap(err)
			}
			return nil
		}()
		if err != nil {
			return gerrors.Wrap(err)
		}
	}
	return nil
}

func (azstorage AzureStorage) UploadDir(ctx context.Context, src string, dst string) error {
	err := filepath.WalkDir(src, func(filePath string, entry fs.DirEntry, err error) error {
		if err != nil {
			return gerrors.Wrap(err)
		}
		if entry.IsDir() {
			return nil
		}
		key := path.Join(dst, strings.TrimPrefix(filePath, src))
		return gerrors.Wrap(azstorage.uploadFile(ctx, filePath, key))
	})
	return gerrors.Wrap(err)
}

func (azstorage AzureStorage) uploadFile(ctx context.Context, src string, key string) error {
	file, err := os.Open(src)
	if err != nil {
		return gerrors.Wrap(err)
	}
	_, err = azstorage.storageClient.UploadFile(ctx, azstorage.container, key, file, nil)
	if err != nil {
		file.Close()
		return gerrors.Wrap(err)
	}
	return gerrors.Wrap(file.Close())
}
