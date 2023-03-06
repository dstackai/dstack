package local

import (
	"context"
	"fmt"
	"io"
	"io/ioutil"
	"os"
	"path"
	"path/filepath"
	"strings"

	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/artifacts"
	"github.com/dstackai/dstack/runner/internal/artifacts/local"
	"github.com/dstackai/dstack/runner/internal/backend"
	"github.com/dstackai/dstack/runner/internal/common"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/models"
	"github.com/dstackai/dstack/runner/internal/states"
	"gopkg.in/yaml.v3"
)

var _ backend.Backend = (*Local)(nil)

func init() {

	backend.DefaultBackend = New()
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
		return New(), nil
	})
}

type Local struct {
	path      string
	runnerID  string
	state     *models.State
	cliSecret *ClientSecret
}

func New() *Local {
	path := filepath.Join(common.HomeDir(), consts.DSTACK_DIR_PATH)
	return &Local{
		path:      path,
		cliSecret: NewClientSecret(path),
	}
}

func (l Local) GetJobByPath(ctx context.Context, path string) (*models.Job, error) {
	if l.state == nil {
		log.Trace(ctx, "State not exist")
		return nil, gerrors.Wrap(backend.ErrLoadStateFile)
	}
	theFile, err := os.Open(filepath.Join(l.path, path))
	if err != nil {
		log.Error(ctx, "Failed to open file", "err", err)
		return nil, gerrors.Wrap(err)
	}
	bodyFile, err := io.ReadAll(theFile)
	if err != nil {
		log.Error(ctx, "Failed to read file", "err", err)
		return nil, gerrors.Wrap(err)
	}
	job := new(models.Job)
	if err = yaml.Unmarshal(bodyFile, job); err != nil {
		return nil, gerrors.Wrap(err)
	}
	return job, nil
}

func (l *Local) GitCredentials(ctx context.Context) *models.GitCredentials {
	log.Trace(ctx, "Getting credentials")
	if l == nil {
		log.Error(ctx, "Backend is empty")
		return nil
	}
	if l.state == nil {
		log.Error(ctx, "State is empty")
		return nil
	}
	if l.state.Job == nil {
		log.Error(ctx, "Job is empty")
		return nil
	}
	return l.cliSecret.fetchCredentials(ctx, l.state.Job.RepoHostNameWithPort(), l.state.Job.RepoUserName, l.state.Job.RepoName)
}

func (l *Local) Secrets(ctx context.Context) (map[string]string, error) {
	log.Trace(ctx, "Getting secrets")
	if l == nil {
		return nil, gerrors.New("Backend is nil")
	}
	if l.state == nil {
		return nil, gerrors.New("State is empty")
	}
	templatePath := fmt.Sprintf("secrets/%s/%s/%s", l.state.Job.RepoHostNameWithPort(), l.state.Job.RepoUserName, l.state.Job.RepoName)
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
			secrets[clearName] = fmt.Sprintf("%s/%s/%s/%s",
				l.state.Job.RepoHostNameWithPort(),
				l.state.Job.RepoUserName,
				l.state.Job.RepoName,
				clearName)
		}
	}
	return l.cliSecret.fetchSecret(ctx, templatePath, secrets)
}

func (l Local) Bucket(ctx context.Context) string {
	return ""
}

func (l Local) ListSubDir(ctx context.Context, dir string) ([]string, error) {
	log.Trace(ctx, "Fetching list sub dir")
	listDir := strings.Split(dir, "/")
	root := strings.Join(listDir[:len(listDir)-1], string(filepath.Separator))
	prefix := listDir[len(listDir)-1]
	list, err := os.ReadDir(filepath.Join(l.path, root))
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	listJob := make([]string, 0, 5)
	for _, value := range list {
		if strings.HasPrefix(value.Name(), prefix) {
			listJob = append(listJob, filepath.Join(root, value.Name()))
		}
	}
	return listJob, nil
}

func (l *Local) Init(ctx context.Context, ID string) error {
	log.Trace(ctx, "Initialize backend with ID runner", "runner ID", ID)
	l.runnerID = ID
	pathRunner := filepath.Join(l.path, "runners", fmt.Sprintf("%s.yaml", ID))
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
	log.Trace(ctx, "Get job", "ID", l.state.Job.JobID)
	return l.state.Job
}

func (l Local) MasterJob(ctx context.Context) *models.Job {
	if l.state == nil {
		log.Trace(ctx, "State not exist")
		return nil
	}
	theFile, err := os.Open(filepath.Join(l.path, "jobs", l.state.Job.RepoUserName, l.state.Job.RepoName, fmt.Sprintf("%s.yaml", l.state.Job.MasterJobID)))
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
	pathDir := filepath.Join(l.path, fmt.Sprintf("jobs/%s/%s/%s", l.state.Job.RepoHostNameWithPort(), l.state.Job.RepoUserName, l.state.Job.RepoName))
	list, err := os.ReadDir(pathDir)
	if err != nil {
		return gerrors.Wrap(err)
	}

	for _, value := range list {
		if !value.IsDir() {
			if strings.HasPrefix(value.Name(), fmt.Sprintf("l;%s;", l.state.Job.JobID)) {
				if err = os.Remove(filepath.Join(pathDir, value.Name())); err != nil {
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
	pathJob := fmt.Sprintf("jobs/%s/%s/%s/%s.yaml", l.state.Job.RepoHostNameWithPort(), l.state.Job.RepoUserName, l.state.Job.RepoName, l.state.Job.JobID)
	log.Trace(ctx, "Write to file job", "Path", pathJob)

	theFile, err := os.OpenFile(filepath.Join(l.path, pathJob), os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0777)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer theFile.Close()

	if _, err = theFile.Write(theFileBody); err != nil {
		return gerrors.Wrap(err)
	}
	appString := make([]string, 0, len(l.state.Job.Apps))
	for _, app := range l.state.Job.Apps {
		appString = append(appString, app.Name)
	}

	artifactSlice := make([]string, 0, 5)
	for _, art := range l.state.Job.Artifacts {
		artifactSlice = append(artifactSlice, strings.ReplaceAll(art.Path, `/`, "_"))
	}

	pathLockJob := fmt.Sprintf("jobs/%s/%s/%s/l;%s;%s;%s;%d;%s;%s;%s;%s",
		l.state.Job.RepoHostNameWithPort(),
		l.state.Job.RepoUserName,
		l.state.Job.RepoName,
		l.state.Job.JobID,
		l.state.Job.ProviderName,
		l.state.Job.LocalRepoUserName,
		l.state.Job.SubmittedAt,
		l.state.Job.Status,
		strings.Join(artifactSlice, ","),
		strings.Join(appString, ","),
		l.state.Job.TagName)
	log.Trace(ctx, "Write to file lock job", "Path", pathLockJob)

	if _, err = os.OpenFile(filepath.Join(l.path, pathLockJob), os.O_WRONLY|os.O_CREATE|os.O_APPEND, 0777); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (l Local) CheckStop(ctx context.Context) (bool, error) {
	if l.state == nil {
		log.Trace(ctx, "State not exist")
		return false, gerrors.Wrap(backend.ErrLoadStateFile)
	}
	pathStateFile := fmt.Sprintf("runners/m;%s;status", l.runnerID)
	log.Trace(ctx, "Reading metadata from state file", "path", pathStateFile)
	if _, err := os.Stat(filepath.Join(l.path, pathStateFile)); err == nil {
		file, err := os.Open(filepath.Join(l.path, pathStateFile))
		if err != nil {
			return false, gerrors.Wrap(err)
		}
		body, err := io.ReadAll(file)
		if err != nil {
			return false, gerrors.Wrap(err)
		}
		if string(body) == states.Stopping {
			log.Trace(ctx, "Status equals stopping")
			return true, nil
		}
		log.Trace(ctx, "Metadata", "status", string(body))
		return false, nil
	}
	return false, nil
}

func (l Local) Shutdown(ctx context.Context) error {
	return nil
}

func (l *Local) GetArtifact(ctx context.Context, runName, localPath, remotePath string, _ bool) artifacts.Artifacter {
	if l == nil {
		return nil
	}
	rootPath := path.Join(common.HomeDir(), consts.USER_ARTIFACTS_PATH, runName)
	log.Trace(ctx, "Create simple artifact's engine. Local", "Root path", rootPath)
	art, err := local.NewLocal(l.path, rootPath, localPath, remotePath)
	if err != nil {
		log.Error(ctx, "Error create simple engine", "err", err)
		return nil
	}
	return art
}

func (l Local) CreateLogger(ctx context.Context, logGroup, logName string) io.Writer {
	if l.state == nil {
		log.Trace(ctx, "State not exist")
		return nil
	}
	log.Trace(ctx, "Build logger", "LogGroup", logGroup, "LogName", logName)
	logger, err := NewLogger(logGroup, logName)
	if err != nil {
		log.Error(ctx, "Failed create logger", "LogGroup", logGroup, "LogName", logName)
		return nil
	}
	return logger
}

type File struct {
	Path string `yaml:"path"`
}
