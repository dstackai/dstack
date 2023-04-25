package gcp

import (
	"context"
	"errors"
	"fmt"
	"github.com/dstackai/dstack/runner/internal/repo"
	"io"
	"io/ioutil"
	"os"
	"path"
	"strings"

	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/artifacts"
	"github.com/dstackai/dstack/runner/internal/backend"
	"github.com/dstackai/dstack/runner/internal/common"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/models"
	"gopkg.in/yaml.v2"
)

type GCPBackend struct {
	project       string
	zone          string
	bucket        string
	storage       *GCPStorage
	compute       *GCPCompute
	secretManager *GCPSecretManager
	logging       *GCPLogging
	runnerID      string
	state         *models.State
}

type GCPConfigFile struct {
	Project string `yaml:"project"`
	Zone    string `yaml:"zone"`
	Bucket  string `yaml:"bucket"`
}

func init() {
	backend.RegisterBackend("gcp", func(ctx context.Context, pathConfig string) (backend.Backend, error) {
		configFile := GCPConfigFile{}
		log.Trace(ctx, "Read config file", "path", pathConfig)
		fileContent, err := ioutil.ReadFile(pathConfig)
		if err != nil {
			return nil, gerrors.Wrap(err)
		}
		log.Trace(ctx, "Unmarshal config")
		err = yaml.Unmarshal(fileContent, &configFile)
		if err != nil {
			return nil, gerrors.Wrap(err)
		}
		return New(configFile.Project, configFile.Zone, configFile.Bucket), nil
	})
}

func New(project, zone, bucket string) *GCPBackend {
	storage, err := NewGCPStorage(project, bucket)
	if err != nil {
		return nil
	}
	compute := NewGCPCompute(project, zone)
	if compute == nil {
		return nil
	}
	secretManager := NewGCPSecretManager(project, bucket)
	if secretManager == nil {
		return nil
	}
	logging := NewGCPLogging(project)
	return &GCPBackend{
		project:       project,
		zone:          zone,
		bucket:        bucket,
		storage:       storage,
		compute:       compute,
		secretManager: secretManager,
		logging:       logging,
	}
}

func (gbackend *GCPBackend) Init(ctx context.Context, ID string) error {
	gbackend.runnerID = ID
	runnerFilepath := fmt.Sprintf("runners/%s.yaml", ID)
	contents, err := gbackend.storage.GetFile(ctx, runnerFilepath)
	if err != nil {
		return gerrors.Wrap(err)
	}
	err = yaml.Unmarshal(contents, &gbackend.state)
	if err != nil {
		return gerrors.Wrap(err)
	}
	if gbackend.state == nil {
		return gerrors.New("State is empty. Data not loading")
	}
	return nil
}

func (gbackend *GCPBackend) Job(ctx context.Context) *models.Job {
	log.Trace(ctx, "Getting job from state")
	log.Trace(ctx, "Get job", "ID", gbackend.state.Job.JobID)
	return gbackend.state.Job
}

func (gbackend *GCPBackend) UpdateState(ctx context.Context) error {
	log.Trace(ctx, "Marshaling job")
	contents, err := yaml.Marshal(&gbackend.state.Job)
	if err != nil {
		return gerrors.Wrap(err)
	}
	jobFilepath := gbackend.state.Job.JobFilepath()
	log.Trace(ctx, "Write to file job", "Path", jobFilepath)
	err = gbackend.storage.PutFile(ctx, jobFilepath, contents)
	if err != nil {
		return gerrors.Wrap(err)
	}
	log.Trace(ctx, "Fetching list jobs", "Repo username", gbackend.state.Job.RepoUserName, "Repo name", gbackend.state.Job.RepoName, "Job ID", gbackend.state.Job.JobID)
	files, err := gbackend.storage.ListFile(ctx, gbackend.state.Job.JobHeadFilepathPrefix())
	if err != nil {
		return gerrors.Wrap(err)
	}
	jobHeadFilepath := gbackend.state.Job.JobHeadFilepath()
	for _, file := range files[:1] {
		log.Trace(ctx, "Renaming file job", "From", file, "To", jobHeadFilepath)
		err = gbackend.storage.RenameFile(ctx, file, jobHeadFilepath)
		if err != nil {
			return gerrors.Wrap(err)
		}
	}
	return nil
}

func (gbackend *GCPBackend) CheckStop(ctx context.Context) (bool, error) {
	runnerFilepath := fmt.Sprintf("runners/%s.yaml", gbackend.runnerID)
	log.Trace(ctx, "Reading metadata from state file", "path", runnerFilepath)
	status, err := gbackend.storage.GetMetadata(ctx, runnerFilepath, "status")
	if err != nil && !errors.Is(err, ErrTagNotFound) {
		return false, gerrors.Wrap(err)
	}
	if status == "stopping" {
		log.Trace(ctx, "Status equals stopping")
		return true, nil
	}
	return false, nil
}

func (gbackend *GCPBackend) IsInterrupted(ctx context.Context) (bool, error) {
	if !gbackend.state.Resources.Interruptible {
		return false, nil
	}
	return gbackend.compute.IsInterruptedSpot(ctx, gbackend.state.RequestID)
}

func (gbackend *GCPBackend) Shutdown(ctx context.Context) error {
	err := gbackend.compute.TerminateInstance(ctx, gbackend.state.RequestID)
	if err != nil {
		return err
	}
	err = gbackend.compute.instancesClient.Close()
	if err != nil {
		return err
	}
	err = gbackend.storage.client.Close()
	if err != nil {
		return err
	}
	err = gbackend.secretManager.client.Close()
	if err != nil {
		return err
	}
	return gbackend.logging.client.Close()
}

func (gbackend *GCPBackend) GetArtifact(ctx context.Context, runName, localPath, remotePath string, mount bool) artifacts.Artifacter {
	workDir := path.Join(common.HomeDir(), consts.USER_ARTIFACTS_PATH, runName)
	return NewGCPArtifacter(gbackend.storage, workDir, localPath, remotePath)
}

func (gbackend *GCPBackend) Requirements(ctx context.Context) models.Requirements {
	log.Trace(ctx, "Getting requirements")
	return gbackend.state.Job.Requirements
}

func (gbackend *GCPBackend) MasterJob(ctx context.Context) *models.Job {
	// TODO
	return nil
}

func (gbackend *GCPBackend) CreateLogger(ctx context.Context, logGroup, logName string) io.Writer {
	logger := gbackend.logging.NewGCPLogger(ctx, gbackend.state.Job.JobID, logGroup, logName)
	if logger == nil {
		log.Error(ctx, "Failed to create logger")
		return nil
	}
	logger.Launch(ctx)
	return logger
}

func (gbackend *GCPBackend) ListSubDir(ctx context.Context, dir string) ([]string, error) {
	return gbackend.storage.ListFile(ctx, dir)
}

func (gbackend *GCPBackend) GetJobByPath(ctx context.Context, path string) (*models.Job, error) {
	log.Trace(ctx, "Fetching job by path", "Path", path)
	content, err := gbackend.storage.GetFile(ctx, path)
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

func (gbackend *GCPBackend) Bucket(ctx context.Context) string {
	log.Trace(ctx, "Getting bucket")
	return gbackend.bucket
}

func (gbackend *GCPBackend) Secrets(ctx context.Context) (map[string]string, error) {
	log.Trace(ctx, "Getting secrets")
	prefix := gbackend.state.Job.SecretsPrefix()
	secretFilenames, err := gbackend.storage.ListFile(ctx, prefix)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	secrets := make(map[string]string, 0)
	for _, secretFilename := range secretFilenames {
		secretName := strings.ReplaceAll(secretFilename, prefix, "")
		secretValue, err := gbackend.secretManager.FetchSecret(ctx, gbackend.state.Job.RepoId, secretName)
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

func (gbackend *GCPBackend) GitCredentials(ctx context.Context) *models.GitCredentials {
	log.Trace(ctx, "Getting credentials")
	creds, err := gbackend.secretManager.FetchCredentials(ctx, gbackend.state.Job.RepoId)
	if err != nil {
		return nil
	}
	return creds
}

func (gbackend *GCPBackend) GetRepoDiff(ctx context.Context, path string) (string, error) {
	diff, err := gbackend.storage.GetFile(ctx, path)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	return string(diff), nil
}

func (gbackend *GCPBackend) GetRepoArchive(ctx context.Context, path, dir string) error {
	archive, err := os.CreateTemp("", "archive-*.tar")
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer os.Remove(archive.Name())

	if err := gbackend.storage.downloadFile(ctx, path, archive.Name()); err != nil {
		return gerrors.Wrap(err)
	}

	if err := repo.ExtractArchive(ctx, archive.Name(), dir); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}
