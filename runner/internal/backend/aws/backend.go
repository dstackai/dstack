package aws

import (
	"context"
	"errors"
	"fmt"
	"io"
	"io/ioutil"
	"path"
	"strings"
	"time"

	"github.com/dstackai/dstack/runner/internal/backend/aws/s3fs"
	"github.com/dstackai/dstack/runner/internal/backend/base"

	"github.com/docker/docker/api/types/mount"
	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/backend"
	"github.com/dstackai/dstack/runner/internal/common"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/models"
	"gopkg.in/yaml.v3"
)

type AWSBackend struct {
	State     *models.State
	region    string
	bucket    string
	runnerID  string
	artifacts []base.Artifacter
	storage   *AWSStorage
	cliEC2    *ClientEC2
	cliSecret *ClientSecret
	logger    *Logger
}

type File struct {
	Region string `yaml:"region"`
	Bucket string `yaml:"bucket"`
}

func init() {
	backend.RegisterBackend("aws", func(ctx context.Context, pathConfig string) (backend.Backend, error) {
		file := File{}
		log.Trace(ctx, "Read config file", "path", pathConfig)
		theConfig, err := ioutil.ReadFile(pathConfig)
		if err != nil {
			return nil, gerrors.Wrap(err)
		}
		log.Trace(ctx, "Unmarshal config")
		err = yaml.Unmarshal(theConfig, &file)
		if err != nil {
			return nil, gerrors.Wrap(err)
		}
		return New(file.Region, file.Bucket), nil
	})
}

func New(region, bucket string) *AWSBackend {
	storage, err := NewAWSStorage(region, bucket)
	if err != nil {
		fmt.Printf("Initialization storage service failure: %+v", err)
		return nil
	}
	return &AWSBackend{
		region:    region,
		bucket:    bucket,
		artifacts: nil,
		storage:   storage,
		cliEC2:    NewClientEC2(region),
		cliSecret: NewClientSecret(region),
	}
}

func (s *AWSBackend) Init(ctx context.Context, ID string) error {
	if s == nil {
		return gerrors.New("Backend is nil")
	}
	s.runnerID = ID
	err := base.LoadRunnerState(ctx, s.storage, ID, &s.State)
	if err != nil {
		return gerrors.Wrap(err)
	}
	if s.State.Job.Location != "" {
		s.cliEC2 = NewClientEC2(s.State.Job.Location)
	}
	return gerrors.Wrap(err)
}

func (s *AWSBackend) Job(ctx context.Context) *models.Job {
	log.Trace(ctx, "Getting job from state")
	if s == nil {
		return new(models.Job)
	}
	if s.State == nil {
		log.Trace(ctx, "State not exist")
		return new(models.Job)
	}
	log.Trace(ctx, "Get job", "job ID", s.State.Job.JobID)
	return s.State.Job
}

func (s *AWSBackend) RefetchJob(ctx context.Context) (*models.Job, error) {
	if err := base.RefetchJob(ctx, s.storage, s.State.Job); err != nil {
		return nil, gerrors.Wrap(err)
	}
	return s.State.Job, nil
}

func (s *AWSBackend) UpdateState(ctx context.Context) error {
	return gerrors.Wrap(base.UpdateState(ctx, s.storage, s.State.Job))
}

func (s *AWSBackend) CheckStop(ctx context.Context) (bool, error) {
	if s == nil {
		return false, gerrors.New("Backend is nil")
	}
	if s.State == nil {
		log.Trace(ctx, "State not exist")
		return false, gerrors.Wrap(backend.ErrLoadStateFile)
	}
	pathStateFile := fmt.Sprintf("runners/%s.yaml", s.runnerID)
	log.Trace(ctx, "Reading metadata from state file", "path", pathStateFile)
	status, err := s.storage.GetMetadata(ctx, pathStateFile, "status")
	if err != nil && !errors.Is(err, ErrTagNotFound) {
		return false, gerrors.Wrap(err)
	}
	if status == "stopping" {
		log.Trace(ctx, "Status equals stopping")
		return true, nil
	}
	return false, nil
}

func (s *AWSBackend) IsInterrupted(ctx context.Context) (bool, error) {
	if !s.State.Resources.Spot {
		return false, nil
	}
	return s.cliEC2.IsInterruptedSpot(ctx, s.State.RequestID)
}

func (s *AWSBackend) Shutdown(ctx context.Context) error {
	log.Trace(ctx, "Start shutdown")
	if s == nil {
		return gerrors.New("Backend is nil")
	}
	if s.State.Resources.Spot {
		log.Trace(ctx, "Instance interruptible")
		if err := s.cliEC2.CancelSpot(ctx, s.State.RequestID); err != nil {
			return gerrors.Wrap(err)
		}
		return nil
	}
	log.Trace(ctx, "Instance not interruptible")
	return s.cliEC2.TerminateInstance(ctx, s.State.RequestID)

}

func (s *AWSBackend) GetArtifact(ctx context.Context, runName, localPath, remotePath string, mount bool) base.Artifacter {
	if s == nil {
		return nil
	}
	if mount {
		rootPath := path.Join(s.GetTMPDir(ctx), consts.FUSE_DIR, runName)
		iamRole := fmt.Sprintf("dstack_role_%s", strings.ReplaceAll(s.bucket, "-", "_"))
		log.Trace(ctx, "Create FUSE artifact's engine", "Region", s.region, "Root path", rootPath, "IAM Role", iamRole)
		art, err := s3fs.New(ctx, s.bucket, s.region, iamRole, rootPath, localPath, remotePath)
		if err != nil {
			log.Error(ctx, "Error FUSE artifact's engine", "err", err)
			return nil
		}
		return art
	}
	rootPath := path.Join(s.GetTMPDir(ctx), consts.USER_ARTIFACTS_DIR, runName)
	log.Trace(ctx, "Create simple artifact's engine", "Region", s.region, "Root path", rootPath)
	art, err := NewAWSArtifacter(s.storage, rootPath, localPath, remotePath, false)
	if err != nil {
		log.Error(ctx, "Failed to create AWSArtifacter", "err", err)
		return nil
	}
	return art
}

func (s *AWSBackend) GetCache(ctx context.Context, runName, localPath, remotePath string) base.Artifacter {
	rootPath := path.Join(s.GetTMPDir(ctx), consts.USER_ARTIFACTS_DIR, runName)
	art, err := NewAWSArtifacter(s.storage, rootPath, localPath, remotePath, true)
	if err != nil {
		log.Error(ctx, "Failed to create AWSArtifacter", "err", err)
		return nil
	}
	return art
}

func (s *AWSBackend) Requirements(ctx context.Context) models.Requirements {
	if s == nil {
		return models.Requirements{}
	}
	if s.State == nil {
		log.Trace(ctx, "State not exist")
		return models.Requirements{}
	}
	log.Trace(ctx, "Return model resource")
	return s.State.Job.Requirements
}

func (s *AWSBackend) MasterJob(ctx context.Context) *models.Job {
	if s == nil {
		return new(models.Job)
	}
	if s.State == nil {
		log.Trace(ctx, "State not exist")
		return nil
	}
	theFile, err := base.GetObject(ctx, s.storage, fmt.Sprintf("jobs/%s/%s.yaml", s.State.Job.RepoId, s.State.Job.MasterJobID))
	if err != nil {
		return nil
	}
	masterJob := new(models.Job)
	err = yaml.Unmarshal(theFile, &masterJob)
	if err != nil {
		return nil
	}
	return masterJob
}

func (s *AWSBackend) CreateLogger(ctx context.Context, logGroup, logName string) io.Writer {
	if s == nil {
		return nil
	}
	if s.State == nil {
		log.Trace(ctx, "State not exist")
		return nil
	}
	var err error
	if s.logger == nil {
		log.Trace(ctx, "Create Cloudwatch")
		s.logger, err = NewCloudwatch(&Config{
			JobID:         s.State.Job.JobID,
			Region:        s.region,
			FlushInterval: 200 * time.Millisecond,
		})
		if err != nil {
			log.Error(ctx, "Fail create Cloudwatch", "err", err)
			return nil
		}
	}
	log.Trace(ctx, "Build std writer", "LogGroup", logGroup, "LogName", logName)
	return s.logger.Build(ctx, logGroup, logName)
}

func (s *AWSBackend) ListSubDir(ctx context.Context, dir string) ([]string, error) {
	return base.ListObjects(ctx, s.storage, dir)
}

func (s *AWSBackend) GetJobByPath(ctx context.Context, path string) (*models.Job, error) {
	job := new(models.Job)
	if err := base.GetJobByPath(ctx, s.storage, path, job); err != nil {
		return nil, gerrors.Wrap(err)
	}
	return job, nil
}

func (s *AWSBackend) Bucket(ctx context.Context) string {
	log.Trace(ctx, "Getting bucket")
	if s == nil {
		return ""
	}
	return s.bucket
}

func (s *AWSBackend) Secrets(ctx context.Context) (map[string]string, error) {
	log.Trace(ctx, "Getting secrets")
	if s == nil {
		return nil, gerrors.New("Backend is nil")
	}
	if s.State == nil {
		return nil, gerrors.New("State is empty")
	}
	prefix := s.State.Job.SecretsPrefix()
	listSecrets, err := base.ListObjects(ctx, s.storage, prefix)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	secrets := make(map[string]string, 0)
	for _, secretPath := range listSecrets {
		clearName := strings.ReplaceAll(secretPath, prefix, "")
		secrets[clearName] = fmt.Sprintf("%s/%s",
			s.State.Job.RepoId,
			clearName)
	}
	return s.cliSecret.fetchSecret(ctx, s.bucket, secrets)
}

func (s *AWSBackend) GitCredentials(ctx context.Context) *models.GitCredentials {
	log.Trace(ctx, "Getting credentials")
	if s == nil {
		log.Error(ctx, "Backend is empty")
		return nil
	}
	if s.State == nil {
		log.Error(ctx, "State is empty")
		return nil
	}
	if s.State.Job == nil {
		log.Error(ctx, "Job is empty")
		return nil
	}
	return s.cliSecret.fetchCredentials(ctx, s.bucket, s.State.Job.RepoId)
}

func (s *AWSBackend) GetRepoDiff(ctx context.Context, path string) (string, error) {
	diff, err := base.GetObject(ctx, s.storage, path)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	return string(diff), nil
}

func (s *AWSBackend) GetRepoArchive(ctx context.Context, path, dir string) error {
	return gerrors.Wrap(base.GetRepoArchive(ctx, s.storage, path, dir))
}

func (s *AWSBackend) GetBuildDiff(ctx context.Context, key, dst string) error {
	_ = base.DownloadFile(ctx, s.storage, key, dst)
	return nil
}

func (s *AWSBackend) PutBuildDiff(ctx context.Context, src, key string) error {
	return gerrors.Wrap(base.UploadFile(ctx, s.storage, src, key))
}

func (s *AWSBackend) GetTMPDir(ctx context.Context) string {
	return path.Join(common.HomeDir(), consts.TMP_DIR_PATH)
}

func (s *AWSBackend) GetDockerBindings(ctx context.Context) []mount.Mount {
	return []mount.Mount{}
}
