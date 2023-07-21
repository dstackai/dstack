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
	"github.com/docker/docker/api/types/mount"
	"gopkg.in/yaml.v2"

	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/backend"
	"github.com/dstackai/dstack/runner/internal/backend/base"
	"github.com/dstackai/dstack/runner/internal/common"
	"github.com/dstackai/dstack/runner/internal/docker"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/models"
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
	if err := base.LoadRunnerState(ctx, azbackend.storage, ID, &azbackend.state); err != nil {
		return gerrors.Wrap(err)
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

func (azbackend *AzureBackend) RefetchJob(ctx context.Context) (*models.Job, error) {
	if err := base.RefetchJob(ctx, azbackend.storage, azbackend.state.Job); err != nil {
		return nil, gerrors.Wrap(err)
	}
	return azbackend.state.Job, nil
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
	return gerrors.Wrap(base.UpdateState(ctx, azbackend.storage, azbackend.state.Job))
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

func (azbackend *AzureBackend) GetArtifact(ctx context.Context, runName, localPath, remotePath string, mount bool) base.Artifacter {
	workDir := path.Join(azbackend.GetTMPDir(ctx), consts.USER_ARTIFACTS_DIR, runName)
	return NewAzureArtifacter(azbackend.storage, workDir, localPath, remotePath, false)
}

func (azbackend *AzureBackend) GetCache(ctx context.Context, runName, localPath, remotePath string) base.Artifacter {
	workDir := path.Join(azbackend.GetTMPDir(ctx), consts.USER_ARTIFACTS_DIR, runName)
	return NewAzureArtifacter(azbackend.storage, workDir, localPath, remotePath, true)
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
	_ = logger.Launch(ctx)
	return logger
}

func (azbackend *AzureBackend) ListSubDir(ctx context.Context, dir string) ([]string, error) {
	return base.ListObjects(ctx, azbackend.storage, dir)
}

func (azbackend *AzureBackend) Bucket(ctx context.Context) string {
	log.Trace(ctx, "Getting bucket")
	return azbackend.config.ResourceGroup
}

func (azbackend *AzureBackend) Secrets(ctx context.Context) (map[string]string, error) {
	log.Trace(ctx, "Getting secrets")
	prefix := azbackend.state.Job.SecretsPrefix()
	secretFilenames, err := base.ListObjects(ctx, azbackend.storage, prefix)
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
	job := new(models.Job)
	if err := base.GetJobByPath(ctx, azbackend.storage, path, job); err != nil {
		return nil, gerrors.Wrap(err)
	}
	return job, nil
}

func (azbackend *AzureBackend) GetRepoDiff(ctx context.Context, path string) (string, error) {
	diff, err := base.GetObject(ctx, azbackend.storage, path)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	return string(diff), nil
}

func (azbackend *AzureBackend) GetRepoArchive(ctx context.Context, path, dir string) error {
	return gerrors.Wrap(base.GetRepoArchive(ctx, azbackend.storage, path, dir))
}

func (azbackend *AzureBackend) GetBuildDiffInfo(ctx context.Context, spec *docker.BuildSpec) (*base.StorageObject, error) {
	obj, err := base.GetBuildDiffInfo(ctx, azbackend.storage, spec)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return obj, nil
}

func (azbackend *AzureBackend) GetBuildDiff(ctx context.Context, key, dst string) error {
	return gerrors.Wrap(base.DownloadFile(ctx, azbackend.storage, key, dst))
}

func (azbackend *AzureBackend) PutBuildDiff(ctx context.Context, src string, spec *docker.BuildSpec) error {
	return gerrors.Wrap(base.PutBuildDiff(ctx, azbackend.storage, src, spec))
}

func (azbackend *AzureBackend) GetTMPDir(ctx context.Context) string {
	return path.Join(common.HomeDir(), consts.TMP_DIR_PATH)
}

func (azbackend *AzureBackend) GetDockerBindings(ctx context.Context) []mount.Mount {
	return []mount.Mount{}
}
