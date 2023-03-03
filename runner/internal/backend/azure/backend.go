package azure

import (
	"bytes"
	"context"
	"fmt"
	"github.com/Azure/azure-sdk-for-go/sdk/azcore/runtime"
	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/Azure/azure-sdk-for-go/sdk/storage/azblob"
	"github.com/Azure/azure-sdk-for-go/sdk/storage/azblob/container"
	"github.com/dstackai/dstack/runner/internal/artifacts"
	"github.com/dstackai/dstack/runner/internal/backend"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/models"
	"gopkg.in/yaml.v2"
	"io"
	"os"
	"strings"
)

type AzureStorage struct {
	Url       string `yaml:"url"`
	Container string `yaml:"container"`
}

type AzureConfig struct {
	Storage AzureStorage `yaml:"storage"`
}

type AzureBackend struct {
	config          AzureConfig
	credential      *azidentity.DefaultAzureCredential
	storageClient   *azblob.Client
	containerClient *container.Client
	runnerID        string
	state           *models.State
}

func init() {
	backend.RegisterBackend("azure", func(ctx context.Context, pathConfig string) (backend.Backend, error) {
		configFile := AzureConfig{}
		log.Trace(ctx, "Read config file", "path", pathConfig)
		fileContent, err := os.ReadFile(pathConfig)
		if err != nil {
			return nil, gerrors.Wrap(err)
		}
		log.Trace(ctx, "Unmarshal config")
		err = yaml.Unmarshal(fileContent, &configFile)
		if err != nil {
			return nil, gerrors.Wrap(err)
		}
		return New(configFile), nil
	})
}

func New(config AzureConfig) *AzureBackend {
	credential, err := azidentity.NewDefaultAzureCredential(nil)
	if err != nil {
		fmt.Printf("Authentication failure: %+v", err)
		return nil
	}

	storageClient, err := azblob.NewClient(config.Storage.Url, credential, nil)
	if err != nil {
		fmt.Printf("Initialization blob service failure: %+v", err)
		return nil
	}
	containerClient := storageClient.ServiceClient().NewContainerClient(config.Storage.Container)

	return &AzureBackend{
		config:          config,
		credential:      credential,
		storageClient:   storageClient,
		containerClient: containerClient,
	}
}

func (azbackend *AzureBackend) Init(ctx context.Context, ID string) error {
	azbackend.runnerID = ID
	// XXX: why does path leak here, while python's backend side works with abstract `key`?
	runnerFilepath := fmt.Sprintf("runners/%s.yaml", ID)
	contents := bytes.Buffer{}
	get, err := azbackend.containerClient.NewBlobClient(runnerFilepath).DownloadStream(ctx, nil)
	if err != nil {
		return gerrors.Wrap(err)
	}
	retryReader := get.NewRetryReader(ctx, &azblob.RetryReaderOptions{})
	_, err2 := contents.ReadFrom(retryReader)
	if err2 != nil {
		return gerrors.Wrap(err)
	}
	err = yaml.Unmarshal(contents.Bytes(), &azbackend.state)
	if err != nil {
		return gerrors.Wrap(err)
	}
	if azbackend.state == nil {
		return gerrors.New("State is empty. Data not loading")
	}
	return nil
}

func (azbackend *AzureBackend) Job(ctx context.Context) *models.Job {
	log.Trace(ctx, "Getting job from state")
	log.Trace(ctx, "Get job", "ID", azbackend.state.Job.JobID)
	return azbackend.state.Job
}

func (azbackend *AzureBackend) MasterJob(ctx context.Context) *models.Job {
	//TODO implement me
	panic("implement me")
}

func (azbackend *AzureBackend) Requirements(ctx context.Context) models.Requirements {
	//TODO implement me
	panic("implement me")
}

func listblobs(ctx context.Context, pager *runtime.Pager[container.ListBlobsFlatResponse]) ([]string, error) {
	var result []string
	for pager.More() {
		resp, err := pager.NextPage(context.TODO())
		if err != nil {
			return nil, gerrors.Wrap(err)
		}

		for _, blob := range resp.Segment.BlobItems {
			result = append(result, strings.Clone(*blob.Name))
		}
	}
	return result, nil
}

func (azbackend *AzureBackend) UpdateState(ctx context.Context) error {
	log.Trace(ctx, "Marshaling job")
	contents, err := yaml.Marshal(&azbackend.state.Job)
	if err != nil {
		return gerrors.Wrap(err)
	}
	jobFilepath := azbackend.state.Job.JobFilepath()
	log.Trace(ctx, "Write to file job", "Path", jobFilepath)
	_, err = azbackend.storageClient.UploadBuffer(ctx, azbackend.config.Storage.Container, jobFilepath, contents, nil)
	if err != nil {
		return gerrors.Wrap(err)
	}
	log.Trace(ctx, "Fetching list jobs", "Repo username", azbackend.state.Job.RepoUserName, "Repo name", azbackend.state.Job.RepoName, "Job ID", azbackend.state.Job.JobID)
	prefix := azbackend.state.Job.JobHeadFilepathPrefix()
	pager := azbackend.containerClient.NewListBlobsFlatPager(&azblob.ListBlobsFlatOptions{Prefix: &prefix})
	blobs, err2 := listblobs(ctx, pager)
	if err2 != nil {
		return gerrors.Wrap(err2)
	}
	if len(blobs) > 1 {
		return fmt.Errorf("Unexpected blob listing result %s [%d]", strings.Join(blobs, ","), len(blobs))
	}
	jobHeadFilepath := azbackend.state.Job.JobHeadFilepath()
	source := azbackend.containerClient.NewBlobClient(blobs[0])
	azbackend.containerClient.NewBlobClient(jobHeadFilepath).CopyFromURL(ctx, source.URL(), nil)
	_, err = source.Delete(ctx, nil)
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (azbackend *AzureBackend) CheckStop(ctx context.Context) (bool, error) {
	//TODO implement me
	panic("implement me")
}

func (azbackend *AzureBackend) Shutdown(ctx context.Context) error {
	//TODO implement me
	log.Trace(ctx, "Start shutdown")
	return nil
}

func (azbackend *AzureBackend) GetArtifact(ctx context.Context, rootPath, localPath, remotePath string, fs bool) artifacts.Artifacter {
	//TODO implement me
	panic("implement me")
}

func (azbackend *AzureBackend) CreateLogger(ctx context.Context, logGroup, logName string) io.Writer {
	//TODO implement me
	panic("implement me")
}

func (azbackend *AzureBackend) ListSubDir(ctx context.Context, dir string) ([]string, error) {
	//TODO implement me
	panic("implement me")
}

func (azbackend *AzureBackend) Bucket(ctx context.Context) string {
	//TODO implement me
	panic("implement me")
}

func (azbackend *AzureBackend) Secrets(ctx context.Context) (map[string]string, error) {
	//TODO implement me
	panic("implement me")
}

func (azbackend *AzureBackend) GitCredentials(ctx context.Context) *models.GitCredentials {
	//TODO implement me
	panic("implement me")
}

func (azbackend *AzureBackend) GetJobByPath(ctx context.Context, path string) (*models.Job, error) {
	//TODO implement me
	panic("implement me")
}
