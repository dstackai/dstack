package backend

import (
	"context"
	"errors"
	"io"
	"io/ioutil"
	"os"
	"path/filepath"
	"sync"

	"github.com/docker/docker/api/types/mount"
	"github.com/dstackai/dstack/runner/internal/artifacts"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/models"
	"gopkg.in/yaml.v2"
)

var ErrLoadStateFile = errors.New("not load state file")

type Backend interface {
	Init(ctx context.Context, ID string) error
	Job(ctx context.Context) *models.Job
	RefetchJob(ctx context.Context) (*models.Job, error)
	MasterJob(ctx context.Context) *models.Job
	Requirements(ctx context.Context) models.Requirements
	UpdateState(ctx context.Context) error
	CheckStop(ctx context.Context) (bool, error)
	IsInterrupted(ctx context.Context) (bool, error)
	Shutdown(ctx context.Context) error
	GetArtifact(ctx context.Context, runName, localPath, remotePath string, fs bool) artifacts.Artifacter
	GetCache(ctx context.Context, runName, localPath, remotePath string) artifacts.Artifacter
	CreateLogger(ctx context.Context, logGroup, logName string) io.Writer
	ListSubDir(ctx context.Context, dir string) ([]string, error)
	Bucket(ctx context.Context) string
	Secrets(ctx context.Context) (map[string]string, error)
	GitCredentials(ctx context.Context) *models.GitCredentials
	GetJobByPath(ctx context.Context, path string) (*models.Job, error)
	GetRepoDiff(ctx context.Context, path string) (string, error)
	GetRepoArchive(ctx context.Context, path, dst string) error
	GetTMPDir(ctx context.Context) string
	GetDockerBindings(ctx context.Context) []mount.Mount
}

type File struct {
	Backend string `yaml:"backend"`
}

var DefaultBackend Backend
var backends map[string]LoadFn
var mu = sync.Mutex{}
var ErrNotFoundTask = errors.New("not found task")

type LoadFn func(ctx context.Context, path string) (Backend, error)

func RegisterBackend(name string, fn LoadFn) {
	mu.Lock()
	defer mu.Unlock()
	if backends == nil {
		backends = make(map[string]LoadFn)
	}
	backends[name] = fn
}

func New(ctx context.Context, path string) (Backend, error) {
	log.Trace(ctx, "Create backend")
	mu.Lock()
	defer mu.Unlock()
	file := File{}
	log.Trace(ctx, "Read config for backend", "path", path)
	if _, err := os.Stat(filepath.Join(path)); err != nil {
		return DefaultBackend, nil
	}
	theConfig, err := ioutil.ReadFile(path)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	log.Trace(ctx, "Unmarshal config")
	err = yaml.Unmarshal(theConfig, &file)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	log.Trace(ctx, "Engine backend", "engine", file.Backend)
	if _, ok := backends[file.Backend]; !ok {
		return nil, gerrors.Newf("backend not found: %s", file.Backend)
	}
	if backends[file.Backend] == nil {
		return nil, gerrors.Newf("backend loading error : %s", file.Backend)
	}
	return backends[file.Backend](ctx, path)
}
