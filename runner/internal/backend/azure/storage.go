package azure

import (
	"context"
	"errors"
	"fmt"
	"github.com/Azure/azure-sdk-for-go/sdk/azcore"
	"github.com/dstackai/dstack/runner/internal/backend/base"
	"io"
	"strings"

	"github.com/Azure/azure-sdk-for-go/sdk/storage/azblob"
	"github.com/Azure/azure-sdk-for-go/sdk/storage/azblob/container"
	"github.com/dstackai/dstack/runner/internal/gerrors"
)

const DSTACK_CONTAINER_NAME = "dstack-container"

var ErrTagNotFound = errors.New("tag not found")

type AzureStorage struct {
	storageClient   *azblob.Client
	containerClient *container.Client
	container       string
}

func NewAzureStorage(credential azcore.TokenCredential, account string) (*AzureStorage, error) {
	storageClient, err := azblob.NewClient(getBlobStorageAccountUrl(account), credential, nil)
	if err != nil {
		fmt.Printf("Initialization blob service failure: %+v", err)
		return nil, err
	}
	containerClient := storageClient.ServiceClient().NewContainerClient(DSTACK_CONTAINER_NAME)
	return &AzureStorage{
		storageClient:   storageClient,
		containerClient: containerClient,
		container:       DSTACK_CONTAINER_NAME,
	}, nil
}

func (azstorage AzureStorage) Download(ctx context.Context, key string, writer io.Writer) error {
	stream, err := azstorage.containerClient.NewBlobClient(key).DownloadStream(ctx, nil)
	if err != nil {
		return gerrors.Wrap(err)
	}
	reader := stream.NewRetryReader(ctx, nil)
	_, err = io.Copy(writer, reader)
	return gerrors.Wrap(err)
}

func (azstorage AzureStorage) Upload(ctx context.Context, reader io.Reader, key string) error {
	_, err := azstorage.containerClient.NewBlockBlobClient(key).UploadStream(ctx, reader, nil)
	return gerrors.Wrap(err)
}

func (azstorage AzureStorage) Delete(ctx context.Context, key string) error {
	_, err := azstorage.containerClient.NewBlobClient(key).Delete(ctx, nil)
	return gerrors.Wrap(err)
}

func (azstorage AzureStorage) Rename(ctx context.Context, oldKey, newKey string) error {
	if oldKey == newKey {
		return nil
	}
	old := azstorage.containerClient.NewBlobClient(oldKey)
	_, err := azstorage.containerClient.NewBlobClient(newKey).CopyFromURL(ctx, old.URL(), nil)
	if err != nil {
		return gerrors.Wrap(err)
	}
	_, err = old.Delete(ctx, nil)
	return gerrors.Wrap(err)
}

func (azstorage AzureStorage) CreateSymlink(ctx context.Context, key, symlink string) error {
	_, err := azstorage.containerClient.NewBlockBlobClient(key).UploadBuffer(ctx, nil, &azblob.UploadBufferOptions{
		Metadata: map[string]*string{
			"symlink": &symlink,
		},
	})
	return gerrors.Wrap(err)
}

func (azstorage AzureStorage) List(ctx context.Context, prefix string) (<-chan *base.StorageObject, <-chan error) {
	pager := azstorage.containerClient.NewListBlobsFlatPager(&azblob.ListBlobsFlatOptions{
		Prefix: &prefix,
		Include: azblob.ListBlobsInclude{
			Metadata: true,
		},
	})
	ch := make(chan *base.StorageObject)
	errCh := make(chan error, 1)
	go func() {
		defer close(ch)
		defer close(errCh)
		for pager.More() {
			resp, err := pager.NextPage(ctx)
			if err != nil {
				errCh <- gerrors.Wrap(err)
				return
			}
			for _, blob := range resp.Segment.BlobItems {
				symlink, ok := blob.Metadata["symlink"]
				if !ok {
					symlink = new(string)
				}
				ch <- &base.StorageObject{
					Key:     strings.TrimPrefix(*blob.Name, prefix),
					Size:    *blob.Properties.ContentLength,
					ModTime: *blob.Properties.LastModified,
					Symlink: *symlink,
				}
			}
		}
	}()
	return ch, errCh
}

func (azstorage AzureStorage) GetMetadata(ctx context.Context, key string, tag string) (string, error) {
	properties, err := azstorage.containerClient.NewBlobClient(key).GetProperties(ctx, nil)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	// azure-sdk-for-go seems to capitalize metadata key
	// https://github.com/Azure/azure-sdk-for-go/issues/17850
	tag = strings.ToUpper(tag[:1]) + tag[1:]
	if value, ok := properties.Metadata[tag]; ok {
		return strings.Clone(*value), nil
	}
	return "", gerrors.Wrap(ErrTagNotFound)
}

func getBlobStorageAccountUrl(account string) string {
	return fmt.Sprintf("https://%s.blob.core.windows.net", account)
}
