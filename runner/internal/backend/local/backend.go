package local

import (
	"context"
	"fmt"
	"io"
	"os"
	"path"
	"path/filepath"
	"strings"

	"github.com/dstackai/dstack/runner/internal/backend/base"
	"github.com/dstackai/dstack/runner/internal/docker"

	"github.com/docker/docker/api/types/mount"
	"github.com/dstackai/dstack/runner/internal/repo"

	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/backend"
	"github.com/dstackai/dstack/runner/internal/common"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/models"
	"gopkg.in/yaml.v3"
)

type LocalConfigFile struct {
	Namespace string `yaml:"namespace"`
}

type Local struct {
	namespace string
	path      string
	runnerID  string
	state     *models.State
	storage   *LocalStorage
	cliSecret *ClientSecret
}

const LOCAL_BACKEND_DIR = "local_backend"

func init() {
	backend.RegisterBackend("local", func(ctx context.Context, pathConfig string) (backend.Backend, error) {
		config := LocalConfigFile{}
		fileContent, err := os.ReadFile(pathConfig)
		if err != nil {
			fmt.Println("[ERROR]", err.Error())
			return nil, err
		}
		err = yaml.Unmarshal(fileContent, &config)
		if err != nil {
			fmt.Println("[ERROR]", err.Error())
			return nil, err
		}
		return New(config.Namespace), nil
	})
}

func New(namespace string) *Local {
	storagePath := filepath.Join(common.HomeDir(), consts.DSTACK_DIR_PATH, LOCAL_BACKEND_DIR, namespace)
	return &Local{
		namespace: namespace,
		path:      storagePath,
		storage:   NewLocalStorage(storagePath),
		cliSecret: NewClientSecret(storagePath),
	}
}

func (l *Local) Init(ctx context.Context, ID string) error {
	log.Trace(ctx, "Initialize backend with ID runner", "runner ID", ID)
	l.runnerID = ID
	if err := base.LoadRunnerState(ctx, l.storage, ID, &l.state); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (l *Local) Job(ctx context.Context) *models.Job {
	log.Trace(ctx, "Getting job from state", "ID", l.state.Job.JobID)
	return l.state.Job
}

func (l *Local) RefetchJob(ctx context.Context) (*models.Job, error) {
	if err := base.RefetchJob(ctx, l.storage, l.state.Job); err != nil {
		return nil, gerrors.Wrap(err)
	}
	return l.state.Job, nil
}

func (l *Local) MasterJob(ctx context.Context) *models.Job {
	contents, err := base.GetObject(ctx, l.storage, filepath.Join("jobs", l.state.Job.RepoData.RepoUserName, l.state.Job.RepoData.RepoName, fmt.Sprintf("%s.yaml", l.state.Job.MasterJobID)))
	if err != nil {
		return nil
	}
	masterJob := new(models.Job)
	err = yaml.Unmarshal(contents, masterJob)
	if err != nil {
		return nil
	}
	return masterJob
}

func (l *Local) Requirements(ctx context.Context) models.Requirements {
	log.Trace(ctx, "Getting requirements")
	return l.state.Job.Requirements
}

func (l *Local) UpdateState(ctx context.Context) error {
	return gerrors.Wrap(base.UpdateState(ctx, l.storage, l.state.Job))
}

func (l *Local) IsInterrupted(ctx context.Context) (bool, error) {
	return false, nil
}

func (l *Local) Stop(ctx context.Context) error {
	return nil
}

func (l *Local) Shutdown(ctx context.Context) error {
	return nil
}

func (l *Local) GetArtifact(ctx context.Context, runName, localPath, remotePath string, _ bool) base.Artifacter {
	rootPath := path.Join(l.GetTMPDir(ctx), consts.USER_ARTIFACTS_DIR, runName)
	log.Trace(ctx, "Create simple artifact's engine. Local", "Root path", rootPath)
	art, err := NewLocalArtifacter(l.path, rootPath, localPath, remotePath)
	if err != nil {
		log.Error(ctx, "Error create simple engine", "err", err)
		return nil
	}
	return art
}

func (l *Local) GetCache(ctx context.Context, runName, localPath, remotePath string) base.Artifacter {
	return l.GetArtifact(ctx, runName, localPath, remotePath, false)
}

func (l *Local) CreateLogger(ctx context.Context, logGroup, logName string) io.Writer {
	log.Trace(ctx, "Build logger", "LogGroup", logGroup, "LogName", logName)
	logger, err := NewLogger(l.state.Job.JobID, l.path, logGroup, logName)
	if err != nil {
		log.Error(ctx, "Failed create logger", "LogGroup", logGroup, "LogName", logName)
		return nil
	}
	return logger
}

func (l *Local) GetJobByPath(ctx context.Context, path string) (*models.Job, error) {
	job := new(models.Job)
	if err := base.GetJobByPath(ctx, l.storage, path, job); err != nil {
		return nil, gerrors.Wrap(err)
	}
	return job, nil
}

func (l *Local) GitCredentials(ctx context.Context) *models.GitCredentials {
	log.Trace(ctx, "Getting credentials")
	return l.cliSecret.fetchCredentials(ctx, l.state.Job.RepoRef.RepoId)
}

func (l *Local) Secrets(ctx context.Context) (map[string]string, error) {
	log.Trace(ctx, "Getting secrets")
	templatePath := fmt.Sprintf("secrets/%s", l.state.Job.RepoRef.RepoId)
	if _, err := os.Stat(filepath.Join(l.path, templatePath)); err != nil {
		return map[string]string{}, nil
	}
	listSecrets, err := os.ReadDir(filepath.Join(l.path, templatePath))
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	secrets := make(map[string]string, 0)
	for _, file := range listSecrets {
		if file.IsDir() {
			continue
		}
		if strings.HasPrefix(file.Name(), "l;") {
			clearName := strings.ReplaceAll(file.Name(), "l;", "")
			secrets[clearName] = fmt.Sprintf("%s/%s",
				l.state.Job.RepoRef.RepoId,
				clearName)
		}
	}
	return l.cliSecret.fetchSecret(ctx, templatePath, secrets)
}

func (l *Local) Bucket(ctx context.Context) string {
	return ""
}

func (l *Local) ListSubDir(ctx context.Context, dir string) ([]string, error) {
	log.Trace(ctx, "Fetching list sub dir")
	return base.ListObjects(ctx, l.storage, dir)
}

func (l *Local) GetRepoDiff(ctx context.Context, path string) (string, error) {
	diff, err := base.GetObject(ctx, l.storage, path)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	return string(diff), nil
}

func (l *Local) GetRepoArchive(ctx context.Context, path, dir string) error {
	src := filepath.Join(l.path, path)
	if err := repo.ExtractArchive(ctx, src, dir); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (l *Local) GetBuildDiffInfo(ctx context.Context, spec *docker.BuildSpec) (*base.StorageObject, error) {
	obj, err := base.GetBuildDiffInfo(ctx, l.storage, spec)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return obj, nil
}

func (l *Local) GetBuildDiff(ctx context.Context, key, dst string) error {
	return gerrors.New("not implemented")
}

func (l *Local) PutBuildDiff(ctx context.Context, src string, spec *docker.BuildSpec) error {
	return gerrors.Wrap(base.PutBuildDiff(ctx, l.storage, src, spec))
}

func (l *Local) GetTMPDir(ctx context.Context) string {
	return path.Join(l.path, "tmp")
}

func (l *Local) GetDockerBindings(ctx context.Context) []mount.Mount {
	return []mount.Mount{
		{
			Type:   mount.TypeBind,
			Source: l.path,
			Target: path.Join(l.state.Job.HomeDir, consts.DSTACK_DIR_PATH, LOCAL_BACKEND_DIR, l.namespace),
		},
	}
}
