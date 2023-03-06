package azure

import (
	"context"
	"fmt"
	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/artifacts"
	"github.com/dstackai/dstack/runner/internal/backend"
	"github.com/dstackai/dstack/runner/internal/common"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/models"
	"gopkg.in/yaml.v2"
	"io"
	"os"
	"path"
	"strings"
)

type AzureConfigStorage struct {
	Url       string `yaml:"url"`
	Container string `yaml:"container"`
}

type AzureConfig struct {
	Storage AzureConfigStorage `yaml:"storage"`
}

type AzureBackend struct {
	config     AzureConfig
	storage    AzureStorage
	credential *azidentity.DefaultAzureCredential
	runnerID   string
	state      *models.State
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
	var storage *AzureStorage
	storage, err = NewAzureStorage(credential, config.Storage.Url, config.Storage.Container)
	if err != nil {
		fmt.Printf("Initialization blob service failure: %+v", err)
		return nil
	}
	return &AzureBackend{
		config:     config,
		credential: credential,
		storage:    *storage,
	}
}

func (azbackend *AzureBackend) Init(ctx context.Context, ID string) error {
	azbackend.runnerID = ID
	runnerFilepath := fmt.Sprintf("runners/%s.yaml", ID)
	contents, err := azbackend.storage.GetFile(ctx, runnerFilepath)
	if err != nil {
		return gerrors.Wrap(err)
	}
	err = yaml.Unmarshal(contents, &azbackend.state)
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

func (azbackend *AzureBackend) UpdateState(ctx context.Context) error {
	log.Trace(ctx, "Marshaling job")
	contents, err := yaml.Marshal(&azbackend.state.Job)
	if err != nil {
		return gerrors.Wrap(err)
	}
	jobFilepath := azbackend.state.Job.JobFilepath()
	log.Trace(ctx, "Write to file job", "Path", jobFilepath)
	err = azbackend.storage.PutFile(ctx, jobFilepath, contents)
	if err != nil {
		return gerrors.Wrap(err)
	}
	log.Trace(ctx, "Fetching list jobs", "Repo username", azbackend.state.Job.RepoUserName, "Repo name", azbackend.state.Job.RepoName, "Job ID", azbackend.state.Job.JobID)
	files, err := azbackend.storage.ListFile(ctx, azbackend.state.Job.JobHeadFilepathPrefix())
	if err != nil {
		return gerrors.Wrap(err)
	}
	if len(files) > 1 {
		return fmt.Errorf("Unexpected blob listing result %s [%d]", strings.Join(files, ","), len(files))
	}
	jobHeadFilepath := azbackend.state.Job.JobHeadFilepath()
	// XXX: this is a clone from gcp/backend.go which uses for-loop and return nil for empty files.
	if len(files) == 1 {
		file := files[0]
		log.Trace(ctx, "Renaming file job", "From", file, "To", jobHeadFilepath)
		err = azbackend.storage.RenameFile(ctx, file, jobHeadFilepath)
		if err != nil {
			return gerrors.Wrap(err)
		}
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

func (azbackend *AzureBackend) GetArtifact(ctx context.Context, runName, localPath, remotePath string, fs bool) artifacts.Artifacter {
	workDir := path.Join(common.HomeDir(), consts.USER_ARTIFACTS_PATH, runName)
	return NewAzureArtifacter(azbackend.storage, workDir, localPath, remotePath)
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
