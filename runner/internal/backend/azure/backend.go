package azure

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"path"
	"strings"

	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/artifacts"
	"github.com/dstackai/dstack/runner/internal/backend"
	"github.com/dstackai/dstack/runner/internal/common"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/models"
	"github.com/dstackai/dstack/runner/internal/repo"
	"gopkg.in/yaml.v2"
)

type AzureConfig struct {
	SubscriptionId string `yaml:"subscription_id"`
	ResourceGroup  string `yaml:"resource_group"`
	StorageAccount string `yaml:"storage_account"`
	VaultUrl       string `yaml:"vault_url"`
}

type AzureBackend struct {
	config        AzureConfig
	storage       AzureStorage
	secretManager AzureSecretManager
	compute       AzureCompute
	credential    *azidentity.DefaultAzureCredential
	runnerID      string
	state         *models.State
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
	storage, err := NewAzureStorage(credential, config.StorageAccount)
	if err != nil {
		fmt.Printf("Initialization blob service failure: %+v", err)
		return nil
	}
	secretManager, err := NewAzureSecretManager(credential, config.VaultUrl)
	if err != nil {
		fmt.Printf("Initialization key vault service failure: %+v", err)
		return nil
	}
	compute, err := NewAzureCompute(credential, config.SubscriptionId, config.ResourceGroup)
	if err != nil {
		fmt.Printf("Initialization compute service failure: %+v", err)
		return nil
	}
	return &AzureBackend{
		config:        config,
		credential:    credential,
		storage:       *storage,
		secretManager: *secretManager,
		compute:       *compute,
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
	ip, err := azbackend.compute.GetInstancePublicIP(ctx, azbackend.state.RequestID)
	if err != nil {
		return gerrors.Wrap(err)
	}
	azbackend.state.Job.HostName = ip
	return nil
}

func (azbackend *AzureBackend) Job(ctx context.Context) *models.Job {
	log.Trace(ctx, "Getting job from state")
	log.Trace(ctx, "Get job", "ID", azbackend.state.Job.JobID)
	return azbackend.state.Job
}

func (azbackend *AzureBackend) MasterJob(ctx context.Context) *models.Job {
	//TODO
	return nil
}

func (azbackend *AzureBackend) Requirements(ctx context.Context) models.Requirements {
	log.Trace(ctx, "Getting requirements")
	return azbackend.state.Job.Requirements
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
		return fmt.Errorf("unexpected blob listing result %s [%d]", strings.Join(files, ","), len(files))
	}
	jobHeadFilepath := azbackend.state.Job.JobHeadFilepath()
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
	runnerFilepath := fmt.Sprintf("runners/%s.yaml", azbackend.runnerID)
	log.Trace(ctx, "Reading metadata from state file", "path", runnerFilepath)
	status, err := azbackend.storage.GetMetadata(ctx, runnerFilepath, "status")
	if err != nil && !errors.Is(err, ErrTagNotFound) {
		return false, gerrors.Wrap(err)
	}
	if status == "stopping" {
		log.Trace(ctx, "Status equals stopping")
		return true, nil
	}
	return false, nil
}

func (azbackend *AzureBackend) IsInterrupted(ctx context.Context) (bool, error) {
	return false, nil
}

func (azbackend *AzureBackend) Shutdown(ctx context.Context) error {
	log.Trace(ctx, "Starting shutdown")
	err := azbackend.compute.TerminateInstance(ctx, azbackend.state.RequestID)
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (azbackend *AzureBackend) GetArtifact(ctx context.Context, runName, localPath, remotePath string, mount bool) artifacts.Artifacter {
	workDir := path.Join(azbackend.GetTMPDir(ctx), consts.USER_ARTIFACTS_DIR, runName)
	return NewAzureArtifacter(azbackend.storage, workDir, localPath, remotePath)
}

func (azbackend *AzureBackend) GetCache(ctx context.Context, runName, localPath, remotePath string) artifacts.Artifacter {
	workDir := path.Join(azbackend.GetTMPDir(ctx), consts.USER_ARTIFACTS_DIR, runName)
	return NewAzureArtifacter(azbackend.storage, workDir, localPath, remotePath)
}

func (azbackend *AzureBackend) CreateLogger(ctx context.Context, logGroup, logName string) io.Writer {
	loggingClient := NewAzureLoggingClient(
		ctx,
		azbackend.credential,
		azbackend.config.SubscriptionId,
		azbackend.config.ResourceGroup,
		azbackend.config.StorageAccount,
	)
	logger := NewAzureLogger(loggingClient, azbackend.state.Job.JobID, logGroup, logName)
	logger.Launch(ctx)
	return logger
}

func (azbackend *AzureBackend) ListSubDir(ctx context.Context, dir string) ([]string, error) {
	return azbackend.storage.ListFile(ctx, dir)
}

func (azbackend *AzureBackend) Bucket(ctx context.Context) string {
	log.Trace(ctx, "Getting bucket")
	return azbackend.config.ResourceGroup
}

func (azbackend *AzureBackend) Secrets(ctx context.Context) (map[string]string, error) {
	log.Trace(ctx, "Getting secrets")
	prefix := azbackend.state.Job.SecretsPrefix()
	secretFilenames, err := azbackend.storage.ListFile(ctx, prefix)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	secrets := make(map[string]string, 0)
	for _, secretFilename := range secretFilenames {
		secretName := strings.ReplaceAll(secretFilename, prefix, "")
		secretValue, err := azbackend.secretManager.FetchSecret(ctx, azbackend.state.Job.RepoId, secretName)
		if err != nil {
			if errors.Is(err, ErrSecretNotFound) {
				continue
			}
			return nil, gerrors.Wrap(err)
		}
		secrets[secretName] = secretValue
	}
	return secrets, nil
}

func (azbackend *AzureBackend) GitCredentials(ctx context.Context) *models.GitCredentials {
	log.Trace(ctx, "Getting credentials")
	creds, err := azbackend.secretManager.FetchCredentials(ctx, azbackend.state.Job.RepoId)
	if err != nil {
		log.Error(ctx, "Getting credentials failure: %+v", err)
		return nil
	}
	return creds
}

func (azbackend *AzureBackend) GetJobByPath(ctx context.Context, path string) (*models.Job, error) {
	log.Trace(ctx, "Fetching job by path", "Path", path)
	content, err := azbackend.storage.GetFile(ctx, path)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	job := new(models.Job)
	err = yaml.Unmarshal(content, &job)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return job, nil
}

func (azbackend *AzureBackend) GetRepoDiff(ctx context.Context, path string) (string, error) {
	diff, err := azbackend.storage.GetFile(ctx, path)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	return string(diff), nil
}

func (azbackend *AzureBackend) GetRepoArchive(ctx context.Context, path, dir string) error {
	archive, err := os.CreateTemp("", "archive-*.tar")
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer os.Remove(archive.Name())

	if err := azbackend.storage.DownloadFile(ctx, path, archive.Name()); err != nil {
		return gerrors.Wrap(err)
	}

	if err := repo.ExtractArchive(ctx, archive.Name(), dir); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (azbackend *AzureBackend) GetPrebuildDiff(ctx context.Context, key, dst string) error {
	_ = azbackend.storage.DownloadFile(ctx, key, dst)
	return nil
}

func (azbackend *AzureBackend) PutPrebuildDiff(ctx context.Context, src, key string) error {
	if err := azbackend.storage.UploadFile(ctx, src, key); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (azbackend *AzureBackend) GetTMPDir(ctx context.Context) string {
	return path.Join(common.HomeDir(), consts.TMP_DIR_PATH)
}
