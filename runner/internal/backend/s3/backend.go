package local

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/ioutil"
	"os"
	"path"
	"strings"
	"time"

	"github.com/dstackai/dstackai/runner/consts"
	"github.com/dstackai/dstackai/runner/internal/artifacts"
	"github.com/dstackai/dstackai/runner/internal/artifacts/s3fs"
	"github.com/dstackai/dstackai/runner/internal/artifacts/simple"
	"github.com/dstackai/dstackai/runner/internal/backend"
	"github.com/dstackai/dstackai/runner/internal/common"
	"github.com/dstackai/dstackai/runner/internal/gerrors"
	"github.com/dstackai/dstackai/runner/internal/log"
	"github.com/dstackai/dstackai/runner/internal/models"
	"gopkg.in/yaml.v3"
)

var _ backend.Backend = (*S3)(nil)

type S3 struct {
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

func New(region, bucket string) *S3 {

	return &S3{
		region:    region,
		bucket:    bucket,
		artifacts: nil,
		cliS3:     NewClientS3(region),
		cliEC2:    NewClientEC2(region),
		cliSecret: NewClientSecret(region),
	}
}

func (s *S3) Init(ctx context.Context, ID string) error {
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
	//Update job for local runner
	if s.state.Resources.Local {
		s.state.Job.RequestID = fmt.Sprintf("l-%d", os.Getpid())
		s.state.Job.RunnerID = ID
	}
	return nil
}

func (s *S3) Job(ctx context.Context) *models.Job {
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

func (s *S3) UpdateState(ctx context.Context) error {
	log.Trace(ctx, "Start update state")
	if s == nil {
		return gerrors.New("Backend is nil")
	}
	if s.state == nil {
		log.Trace(ctx, "State not exist")
		return gerrors.Wrap(backend.ErrLoadStateFile)
	}
	log.Trace(ctx, "Fetching list jobs", "Repo username", s.state.Job.RepoUserName, "Repo name", s.state.Job.RepoName, "Job ID", s.state.Job.JobID)
	listForDelete, err := s.cliS3.ListFile(ctx, s.bucket, fmt.Sprintf("jobs/%s/%s/%s/l;%s;", s.state.Job.RepoHostNameWithPort(), s.state.Job.RepoUserName, s.state.Job.RepoName, s.state.Job.JobID))
	if err != nil {
		return gerrors.Wrap(err)
	}
	for _, fileForDelete := range listForDelete {
		log.Trace(ctx, "Deleting file job", "Bucket", s.bucket, "Path", fileForDelete)
		err = s.cliS3.DeleteFile(ctx, s.bucket, fileForDelete)
		if err != nil {
			return gerrors.Wrap(err)
		}
	}
	log.Trace(ctx, "Marshaling job")
	theFile, err := yaml.Marshal(&s.state.Job)
	if err != nil {
		return gerrors.Wrap(err)
	}
	pathJob := fmt.Sprintf("jobs/%s/%s/%s/%s.yaml", s.state.Job.RepoHostNameWithPort(), s.state.Job.RepoUserName, s.state.Job.RepoName, s.state.Job.JobID)
	log.Trace(ctx, "Write to file job", "Path", pathJob)
	err = s.cliS3.PutFile(ctx, s.bucket, pathJob, theFile)
	if err != nil {
		return gerrors.Wrap(err)
	}
	appString := ""
	for _, app := range s.state.Job.Apps {
		appString += app.Name
	}

	artifactSlice := make([]string, 0)
	for _, art := range s.state.Job.Artifacts {
		artifactSlice = append(artifactSlice, art.Path)
	}

	pathLockJob := fmt.Sprintf("jobs/%s/%s/%s/l;%s;%s;%s;%d;%s;%s;%s;%s",
		s.state.Job.RepoHostNameWithPort(),
		s.state.Job.RepoUserName,
		s.state.Job.RepoName,
		s.state.Job.JobID,
		s.state.Job.ProviderName,
		s.state.Job.LocalRepoUserName,
		s.state.Job.SubmittedAt,
		s.state.Job.Status,
		strings.Join(artifactSlice, ","),
		appString,
		s.state.Job.TagName)
	log.Trace(ctx, "Write to file lock job", "Path", pathLockJob)
	err = s.cliS3.PutFile(ctx, s.bucket, pathLockJob, []byte{})
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}
func (s *S3) CheckStop(ctx context.Context) (bool, error) {
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

func (s *S3) Shutdown(ctx context.Context) error {
	log.Trace(ctx, "Start shutdown")
	if s == nil {
		return gerrors.New("Backend is nil")
	}
	if s.state.Resources.Local {
		return nil
	}
	if s.state.Resources.Interruptible {
		log.Trace(ctx, "Instance interruptible")
		if err := s.cliEC2.CancelSpot(ctx, s.state.RequestID); err != nil {
			return gerrors.Wrap(err)
		}
		return nil
	}
	log.Trace(ctx, "Instance not interruptible")
	return s.cliEC2.TerminateInstance(ctx, s.state.RequestID)

}

func (s *S3) GetArtifact(ctx context.Context, runName, localPath, remotePath string, mount bool) artifacts.Artifacter {
	if s == nil {
		return nil
	}
	if mount {
		rootPath := path.Join(common.HomeDir(), consts.FUSE_PATH, runName)
		iamRole := fmt.Sprintf("dstack_role_%s", strings.ReplaceAll(s.bucket, "-", "_"))
		log.Trace(ctx, "Create FUSE artifact's engine", "Region", s.region, "Root path", rootPath, "IAM Role", iamRole)
		art, err := s3fs.New(ctx, s.bucket, s.region, iamRole, rootPath, localPath, remotePath)
		if err != nil {
			log.Error(ctx, "Error FUSE artifact's engine", "err", err)
			return nil
		}
		return art
	}
	rootPath := path.Join(common.HomeDir(), consts.USER_ARTIFACTS_PATH, runName)
	log.Trace(ctx, "Create simple artifact's engine", "Region", s.region, "Root path", rootPath)
	art, err := simple.NewSimple(s.bucket, s.region, rootPath, localPath, remotePath)
	if err != nil {
		log.Error(ctx, "Error create simple engine", "err", err)
		return nil
	}
	return art
}

func (s *S3) Requirements(ctx context.Context) models.Requirements {
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

func (s *S3) MasterJob(ctx context.Context) *models.Job {
	if s == nil {
		return new(models.Job)
	}
	if s.state == nil {
		log.Trace(ctx, "State not exist")
		return nil
	}
	theFile, err := s.cliS3.GetFile(ctx, s.bucket, fmt.Sprintf("jobs/%s/%s/%s/%s.yaml", s.state.Job.RepoHostNameWithPort(), s.state.Job.RepoUserName, s.state.Job.RepoName, s.state.Job.MasterJobID))
	if err != nil {
		return nil
	}
	masterJob := new(models.Job)
	err = yaml.Unmarshal(theFile, masterJob)
	if err != nil {
		return nil
	}
	return masterJob
}

func (s *S3) CreateLogger(ctx context.Context, logGroup, logName string) io.Writer {
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

func (s *S3) ListSubDir(ctx context.Context, dir string) ([]string, error) {
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
func (s *S3) GetJobByPath(ctx context.Context, path string) (*models.Job, error) {
	log.Trace(ctx, "Fetching job by path", "Path", path)
	if s == nil {
		return nil, gerrors.New("Backend is nil")
	}
	fileJob, err := s.cliS3.GetFile(ctx, s.bucket, path)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	var job *models.Job
	err = json.Unmarshal(fileJob, job)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return job, nil
}

func (s *S3) Bucket(ctx context.Context) string {
	log.Trace(ctx, "Getting bucket")
	if s == nil {
		return ""
	}
	return s.bucket
}
func (s *S3) Secrets(ctx context.Context) (map[string]string, error) {
	log.Trace(ctx, "Getting secrets")
	if s == nil {
		return nil, gerrors.New("Backend is nil")
	}
	if s.state == nil {
		return nil, gerrors.New("State is empty")
	}
	templatePath := fmt.Sprintf("secrets/%s/%s/%s/l;", s.state.Job.RepoHostNameWithPort(), s.state.Job.RepoUserName, s.state.Job.RepoName)
	listSecrets, err := s.cliS3.ListFile(ctx, s.bucket, templatePath)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	secrets := make([]string, 0, len(listSecrets))
	for _, secretPath := range listSecrets {
		secrets = append(secrets, strings.ReplaceAll(secretPath, templatePath, ""))
	}
	return s.cliSecret.fetchSecret(ctx, s.bucket, secrets)
}
func (s *S3) GitCredentials(ctx context.Context) *models.GitCredentials {
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
	return s.cliSecret.fetchCredentials(ctx, s.bucket, s.state.Job.RepoHostNameWithPort(), s.state.Job.RepoUserName, s.state.Job.RepoName)
}
