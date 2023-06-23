package aws

import (
	"context"
	"errors"
	"fmt"
	"io"
	"io/ioutil"
	"os"
	"path"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/docker/docker/api/types/mount"
	"github.com/dstackai/dstack/runner/internal/repo"

	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/artifacts"
	"github.com/dstackai/dstack/runner/internal/artifacts/s3fs"
	"github.com/dstackai/dstack/runner/internal/artifacts/simple"
	"github.com/dstackai/dstack/runner/internal/backend"
	"github.com/dstackai/dstack/runner/internal/common"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/models"
	"gopkg.in/yaml.v3"
)

type AWSBackend struct {
	region    string
	bucket    string
	runnerID  string
	state     *models.State
	artifacts []artifacts.Artifacter
	cliS3     *ClientS3
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
	return &AWSBackend{
		region:    region,
		bucket:    bucket,
		artifacts: nil,
		cliS3:     NewClientS3(region),
		cliEC2:    NewClientEC2(region),
		cliSecret: NewClientSecret(region),
	}
}

func (s *AWSBackend) Init(ctx context.Context, ID string) error {
	log.Trace(ctx, "Initialize backend with ID runner", "runner ID", ID)
	if s == nil {
		return gerrors.New("Backend is nil")
	}
	s.runnerID = ID
	pathS3 := fmt.Sprintf("runners/%s.yaml", ID)
	log.Trace(ctx, "Fetch runner state from S3",
		"region", s.region,
		"bucket", s.bucket,
		"path", pathS3)
	theFile, err := s.cliS3.GetFile(ctx, s.bucket, pathS3)
	if err != nil {
		return gerrors.Wrap(err)
	}
	log.Trace(ctx, "Unmarshal state")
	err = yaml.Unmarshal(theFile, &s.state)
	if err != nil {
		return gerrors.Wrap(err)
	}
	if s.state == nil {
		return gerrors.New("State is empty. Data not loading")
	}
	return nil
}

func (s *AWSBackend) Job(ctx context.Context) *models.Job {
	log.Trace(ctx, "Getting job from state")
	if s == nil {
		return new(models.Job)
	}
	if s.state == nil {
		log.Trace(ctx, "State not exist")
		return new(models.Job)
	}
	log.Trace(ctx, "Get job", "job ID", s.state.Job.JobID)
	return s.state.Job
}

func (s *AWSBackend) RefetchJob(ctx context.Context) (*models.Job, error) {
	log.Trace(ctx, "Refetching job from state", "ID", s.state.Job.JobID)
	contents, err := s.cliS3.GetFile(ctx, s.bucket, s.state.Job.JobFilepath())
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	err = yaml.Unmarshal(contents, &s.state.Job)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return s.state.Job, nil
}

func (s *AWSBackend) UpdateState(ctx context.Context) error {
	log.Trace(ctx, "Start update state")
	if s == nil {
		return gerrors.New("Backend is nil")
	}
	if s.state == nil {
		log.Trace(ctx, "State not exist")
		return gerrors.Wrap(backend.ErrLoadStateFile)
	}
	log.Trace(ctx, "Marshaling job")
	theFile, err := yaml.Marshal(&s.state.Job)
	if err != nil {
		return gerrors.Wrap(err)
	}
	jobFilepath := s.state.Job.JobFilepath()
	log.Trace(ctx, "Write to file job", "Path", jobFilepath)
	err = s.cliS3.PutFile(ctx, s.bucket, jobFilepath, theFile)
	if err != nil {
		return gerrors.Wrap(err)
	}
	log.Trace(ctx, "Fetching list jobs", "Repo username", s.state.Job.RepoUserName, "Repo name", s.state.Job.RepoName, "Job ID", s.state.Job.JobID)
	files, err := s.cliS3.ListFile(ctx, s.bucket, s.state.Job.JobHeadFilepathPrefix())
	if err != nil {
		return gerrors.Wrap(err)
	}
	jobHeadFilepath := s.state.Job.JobHeadFilepath()
	for _, file := range files[:1] {
		log.Trace(ctx, "Renaming file job", "From", file, "To", jobHeadFilepath)
		err = s.cliS3.RenameFile(ctx, s.bucket, file, jobHeadFilepath)
		if err != nil {
			return gerrors.Wrap(err)
		}
	}
	return nil
}

func (s *AWSBackend) CheckStop(ctx context.Context) (bool, error) {
	if s == nil {
		return false, gerrors.New("Backend is nil")
	}
	if s.state == nil {
		log.Trace(ctx, "State not exist")
		return false, gerrors.Wrap(backend.ErrLoadStateFile)
	}
	pathStateFile := fmt.Sprintf("runners/%s.yaml", s.runnerID)
	log.Trace(ctx, "Reading metadata from state file", "path", pathStateFile)
	status, err := s.cliS3.MetadataFile(ctx, s.bucket, pathStateFile, "status")
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
	if !s.state.Resources.Spot {
		return false, nil
	}
	return s.cliEC2.IsInterruptedSpot(ctx, s.state.RequestID)
}

func (s *AWSBackend) Shutdown(ctx context.Context) error {
	log.Trace(ctx, "Start shutdown")
	if s == nil {
		return gerrors.New("Backend is nil")
	}
	if s.state.Resources.Spot {
		log.Trace(ctx, "Instance interruptible")
		if err := s.cliEC2.CancelSpot(ctx, s.state.RequestID); err != nil {
			return gerrors.Wrap(err)
		}
		return nil
	}
	log.Trace(ctx, "Instance not interruptible")
	return s.cliEC2.TerminateInstance(ctx, s.state.RequestID)

}

func (s *AWSBackend) GetArtifact(ctx context.Context, runName, localPath, remotePath string, mount bool) artifacts.Artifacter {
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
	art, err := simple.NewSimple(s.bucket, s.region, rootPath, localPath, remotePath, false)
	if err != nil {
		log.Error(ctx, "Error create simple engine", "err", err)
		return nil
	}
	return art
}

func (s *AWSBackend) GetCache(ctx context.Context, runName, localPath, remotePath string) artifacts.Artifacter {
	rootPath := path.Join(s.GetTMPDir(ctx), consts.USER_ARTIFACTS_DIR, runName)
	art, err := simple.NewSimple(s.bucket, s.region, rootPath, localPath, remotePath, true)
	if err != nil {
		log.Error(ctx, "Error create simple engine", "err", err)
		return nil
	}
	return art
}

func (s *AWSBackend) Requirements(ctx context.Context) models.Requirements {
	if s == nil {
		return models.Requirements{}
	}
	if s.state == nil {
		log.Trace(ctx, "State not exist")
		return models.Requirements{}
	}
	log.Trace(ctx, "Return model resource")
	return s.state.Job.Requirements
}

func (s *AWSBackend) MasterJob(ctx context.Context) *models.Job {
	if s == nil {
		return new(models.Job)
	}
	if s.state == nil {
		log.Trace(ctx, "State not exist")
		return nil
	}
	theFile, err := s.cliS3.GetFile(ctx, s.bucket, fmt.Sprintf("jobs/%s/%s.yaml", s.state.Job.RepoId, s.state.Job.MasterJobID))
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
	if s.state == nil {
		log.Trace(ctx, "State not exist")
		return nil
	}
	var err error
	if s.logger == nil {
		log.Trace(ctx, "Create Cloudwatch")
		s.logger, err = NewCloudwatch(&Config{
			JobID:         s.state.Job.JobID,
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
	log.Trace(ctx, "Fetching list sub dir")
	if s == nil {
		return nil, gerrors.New("Backend is nil")
	}
	listDir, err := s.cliS3.ListDir(ctx, s.bucket, dir)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return listDir, nil
}

func (s *AWSBackend) GetJobByPath(ctx context.Context, path string) (*models.Job, error) {
	log.Trace(ctx, "Fetching job by path", "Path", path)
	if s == nil {
		return nil, gerrors.New("Backend is nil")
	}
	fileJob, err := s.cliS3.GetFile(ctx, s.bucket, path)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	var job *models.Job
	err = yaml.Unmarshal(fileJob, &job)
	if err != nil {
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
	if s.state == nil {
		return nil, gerrors.New("State is empty")
	}
	templatePath := fmt.Sprintf("secrets/%s/l;", s.state.Job.RepoId)
	listSecrets, err := s.cliS3.ListFile(ctx, s.bucket, templatePath)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	secrets := make(map[string]string, 0)
	for _, secretPath := range listSecrets {
		clearName := strings.ReplaceAll(secretPath, templatePath, "")
		secrets[clearName] = fmt.Sprintf("%s/%s",
			s.state.Job.RepoId,
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
	if s.state == nil {
		log.Error(ctx, "State is empty")
		return nil
	}
	if s.state.Job == nil {
		log.Error(ctx, "Job is empty")
		return nil
	}
	return s.cliSecret.fetchCredentials(ctx, s.bucket, s.state.Job.RepoId)
}

func (s *AWSBackend) GetRepoDiff(ctx context.Context, path string) (string, error) {
	diff, err := s.cliS3.GetFile(ctx, s.bucket, path)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	return string(diff), nil
}

func (s *AWSBackend) GetRepoArchive(ctx context.Context, path, dir string) error {
	archive, err := os.CreateTemp("", "archive-*.tar")
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer os.Remove(archive.Name())

	out, err := s.cliS3.cli.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(s.bucket),
		Key:    aws.String(path),
	})
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer out.Body.Close()
	size, err := io.Copy(archive, out.Body)
	if err != nil {
		return gerrors.Wrap(err)
	}
	if size != out.ContentLength {
		return gerrors.New("size not equal")
	}
	if err := repo.ExtractArchive(ctx, archive.Name(), dir); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (s *AWSBackend) GetBuildDiff(ctx context.Context, key, dst string) error {
	out, err := s.cliS3.cli.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(s.bucket),
		Key:    aws.String(key),
	})
	if err != nil { // it's okay not to have a diff
		return nil
	}
	defer func() { _ = out.Body.Close() }()
	file, err := os.Create(dst)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = file.Close() }()
	_, err = io.Copy(file, out.Body)
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (s *AWSBackend) PutBuildDiff(ctx context.Context, src, key string) error {
	file, err := os.Open(src)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = file.Close() }()
	_, err = s.cliS3.cli.PutObject(ctx, &s3.PutObjectInput{
		Bucket: aws.String(s.bucket),
		Key:    aws.String(key),
		Body:   file,
	})
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (s *AWSBackend) GetTMPDir(ctx context.Context) string {
	return path.Join(common.HomeDir(), consts.TMP_DIR_PATH)
}

func (s *AWSBackend) GetDockerBindings(ctx context.Context) []mount.Mount {
	return []mount.Mount{}
}
