package local

import (
	"context"
	"fmt"
	"io"
	"io/ioutil"
	"os"
	"path/filepath"
	"strings"

	"github.com/dstackai/dstackai/runner/consts"
	"github.com/dstackai/dstackai/runner/internal/artifacts"
	"github.com/dstackai/dstackai/runner/internal/backend"
	"github.com/dstackai/dstackai/runner/internal/common"
	"github.com/dstackai/dstackai/runner/internal/gerrors"
	"github.com/dstackai/dstackai/runner/internal/log"
	"github.com/dstackai/dstackai/runner/internal/models"
)

var _ backend.Backend = (*Local)(nil)

type Local struct {
	path      string
	runnerID  string
	state     *models.State
	artifacts []artifacts.Artifacter
	logger    *Logger
}

func (l Local) fullPath(ctx context.Context) string {
	return filepath.Join(common.HomeDir(), consts.DSTACK_DIR_PATH, l.Bucket(ctx))
}

func (l Local) GitCredentials(ctx context.Context) *models.GitCredentials {
	git := &models.GitCredentials{
		Protocol: os.Getenv("REPO_PROTOCOL"),
	}
	if os.Getenv("REPO_OAUTH_TOKEN") != "" {
		git.OAuthToken = common.String(os.Getenv("REPO_OAUTH_TOKEN"))
	}
	if os.Getenv("REPO_PRIVATE_KEY") != "" {
		git.PrivateKey = common.String(os.Getenv("REPO_PRIVATE_KEY"))
	}
	if os.Getenv("REPO_PASSPHRASE") != "" {
		git.Passphrase = common.String(os.Getenv("REPO_PASSPHRASE"))
	}
	return git
}

func (l Local) Secrets(ctx context.Context) map[string]string {
	return map[string]string{}
}

func (l Local) Bucket(ctx context.Context) string {
	if l.path == "" {
		return "default"
	}
	return l.path
}

func (l Local) ListSubDir(ctx context.Context, dir string) ([]string, error) {
	log.Trace(ctx, "Fetching list sub dir")
	list, err := os.ReadDir(filepath.Join(l.fullPath(ctx), dir))
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	listDir := make([]string, 0, 5)
	for _, value := range list {
		if value.IsDir() {
			listDir = append(listDir, value.Name())
		}
	}
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return listDir, nil
}

func (l Local) Init(ctx context.Context, ID string) error {
	log.Trace(ctx, "Initialize backend with ID runner", "runner ID", ID)
	l.runnerID = ID
	pathRunner := filepath.Join(l.fullPath(ctx), "runners", fmt.Sprintf("%s.yaml", ID))
	log.Trace(ctx, "Fetch runner state from S3",
		"path", pathRunner)
	theFile, err := os.Open(pathRunner)
	if err != nil {
		return gerrors.Wrap(err)
	}
	log.Trace(ctx, "Unmarshal state")
	bodyFile, err := io.ReadAll(theFile)
	if err != nil {
		return gerrors.Wrap(err)
	}
	err = yaml.Unmarshal(bodyFile, &l.state)
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (l Local) Job(ctx context.Context) *models.Job {
	log.Trace(ctx, "Getting job from state")
	if l.state == nil {
		log.Trace(ctx, "State not exist")
		return new(models.Job)
	}
	log.Trace(ctx, "Get job", "job ID", l.state.Job.JobID)
	return l.state.Job
}

func (l Local) MasterJob(ctx context.Context) *models.Job {
	if l.state == nil {
		log.Trace(ctx, "State not exist")
		return nil
	}
	theFile, err := os.Open(filepath.Join(l.fullPath(ctx), "jobs", l.state.Job.RepoUserName, l.state.Job.RepoName, fmt.Sprintf("%s.yaml", l.state.Job.MasterJobID)))
	if err != nil {
		log.Error(ctx, "Failed to open file", "err", err)
		return nil
	}
	bodyFile, err := io.ReadAll(theFile)
	if err != nil {
		log.Error(ctx, "Failed to read file", "err", err)
		return nil
	}
	masterJob := new(models.Job)
	err = yaml.Unmarshal(bodyFile, masterJob)
	if err != nil {
		return nil
	}
	return masterJob
}

func (l Local) Requirements(ctx context.Context) models.Requirements {
	if l.state == nil {
		log.Trace(ctx, "State not exist")
		return models.Requirements{}
	}
	log.Trace(ctx, "Return model resource")
	return l.state.Job.Requirements
}

func (l Local) UpdateState(ctx context.Context) error {
	log.Trace(ctx, "Start update state")
	if l.state == nil {
		log.Trace(ctx, "State not exist")
		return gerrors.Wrap(backend.ErrLoadStateFile)
	}
	log.Trace(ctx, "Fetching list jobs", "Repo username", l.state.Job.RepoUserName, "Repo name", l.state.Job.RepoName, "Job ID", l.state.Job.JobID)
	list, err := os.ReadDir(filepath.Join(l.fullPath(ctx), fmt.Sprintf("jobs/%s/%s", l.state.Job.RepoUserName, l.state.Job.RepoName)))
	if err != nil {
		return gerrors.Wrap(err)
	}

	for _, value := range list {
		if !value.IsDir() {
			if strings.HasPrefix(value.Name(), fmt.Sprintf("l;%s;", l.state.Job.JobID)) {
				if err = os.Remove(filepath.Join(l.fullPath(ctx), fmt.Sprintf("jobs/%s/%s", l.state.Job.RepoUserName, l.state.Job.RepoName), value.Name())); err != nil {
					return gerrors.Wrap(err)
				}
			}
		}
	}
	log.Trace(ctx, "Marshaling job")
	theFileBody, err := yaml.Marshal(&l.state.Job)
	if err != nil {
		return gerrors.Wrap(err)
	}
	pathJob := fmt.Sprintf("jobs/%s/%s/%s.yaml", l.state.Job.RepoUserName, l.state.Job.RepoName, l.state.Job.JobID)
	log.Trace(ctx, "Write to file job", "Path", pathJob)

	theFile, err := os.OpenFile(filepath.Join(l.fullPath(ctx), pathJob), os.O_WRONLY|os.O_CREATE, 0777)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer theFile.Close()
	_, err = theFile.Write(theFileBody)
	if err != nil {
		return gerrors.Wrap(err)
	}
	appString := ""
	for _, app := range l.state.Job.Apps {
		appString += app.Name
	}

	artifactSlice := make([]string, 0, 5)
	for _, art := range l.state.Job.Artifacts {
		artifactSlice = append(artifactSlice, art.Path)
	}

	pathLockJob := fmt.Sprintf("jobs/%s/%s/l;%s;%s;%d;%s;%s;%s;%s",
		l.state.Job.RepoUserName,
		l.state.Job.RepoName,
		l.state.Job.JobID,
		l.state.Job.ProviderName,
		l.state.Job.SubmittedAt,
		l.state.Job.Status,
		strings.Join(artifactSlice, ","),
		appString,
		l.state.Job.TagName)
	log.Trace(ctx, "Write to file lock job", "Path", pathLockJob)

	if _, err = os.OpenFile(filepath.Join(l.fullPath(ctx), pathLockJob), os.O_WRONLY|os.O_CREATE|os.O_APPEND, 0777); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (l Local) CheckStop(ctx context.Context) (bool, error) {
	if l.state == nil {
		log.Trace(ctx, "State not exist")
		return false, gerrors.Wrap(backend.ErrLoadStateFile)
	}
	pathStateFile := fmt.Sprintf("runners/%s.stop", l.runnerID)
	log.Trace(ctx, "Reading metadata from state file", "path", pathStateFile)
	if _, err := os.Stat(filepath.Join(l.fullPath(ctx), pathStateFile)); err == nil {
		log.Trace(ctx, "Status equals stopping")
		return true, nil
	}
	return false, nil
}

func (l Local) Shutdown(ctx context.Context) error {
	return nil
}

func (l Local) GetArtifact(ctx context.Context, runName, localPath, remotePath string, _ bool) artifacts.Artifacter {
	panic("not implement")
}

func (l Local) CreateLogger(ctx context.Context, logGroup, logName string) io.Writer {
	if l.state == nil {
		log.Trace(ctx, "State not exist")
		return nil
	}
	var err error
	if l.logger == nil {
		log.Trace(ctx, "Create Cloudwatch")
		if l.logger, err = NewLogger(logGroup, logName); err != nil {
			log.Error(ctx, "Fail create Cloudwatch", "err", err)
			return nil
		}
	}
	log.Trace(ctx, "Build std writer", "LogGroup", logGroup, "LogName", logName)
	return l.logger.logger.Writer()
}

type File struct {
	Path string `yaml:"path"`
}

func init() {
	backend.RegisterBackend("local", func(ctx context.Context, pathConfig string) (backend.Backend, error) {
		file := File{}
		theConfig, err := ioutil.ReadFile(pathConfig)
		if err != nil {
			fmt.Println("[ERROR]", err.Error())
			return nil, err
		}
		err = yaml.Unmarshal(theConfig, &file)
		if err != nil {
			fmt.Println("[ERROR]", err.Error())
			return nil, err
		}
		return New(file.Path), nil
	})
}

func New(path string) *Local {
	if path == "" {
		fmt.Println("[ERROR]", "path is empty")
		return nil
	}
	return &Local{path: path}
}
