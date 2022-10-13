package local

import (
	"context"
	"fmt"
	"io"
	"io/ioutil"

	"gitlab.com/dstackai/dstackai-runner/internal/artifacts"
	"gitlab.com/dstackai/dstackai-runner/internal/backend"
	"gitlab.com/dstackai/dstackai-runner/internal/models"
	"gopkg.in/yaml.v3"
)

var _ backend.Backend = (*Local)(nil)

type Local struct {
	path      string
	state     *models.State
	artifacts []artifacts.Artifacter
}

func (l Local) GitCredentials(ctx context.Context) *models.GitCredentials {
	//TODO implement me
	panic("implement me")
}

func (l Local) Secrets(ctx context.Context) map[string]string {
	//TODO implement me
	panic("implement me")
}

func (l Local) Bucket(ctx context.Context) string {
	panic("implement me")
}

func (l Local) ListSubDir(ctx context.Context, dir string) ([]string, error) {
	//TODO implement me
	panic("implement me")
}

func (l Local) Init(ctx context.Context, ID string) error {
	//TODO implement me
	panic("implement me")
}

func (l Local) Job(ctx context.Context) *models.Job {
	//TODO implement me
	panic("implement me")
}

func (l Local) MasterJob(ctx context.Context) *models.Job {
	//TODO implement me
	panic("implement me")
}

func (l Local) Requirements(ctx context.Context) models.Requirements {
	//TODO implement me
	panic("implement me")
}

func (l Local) UpdateState(ctx context.Context) error {
	//TODO implement me
	panic("implement me")
}

func (l Local) CheckStop(ctx context.Context) (bool, error) {
	//TODO implement me
	panic("implement me")
}

func (l Local) Shutdown(ctx context.Context) error {
	//TODO implement me
	panic("implement me")
}

func (l Local) GetArtifact(ctx context.Context, rootPath, localPath, remotePath string, fs bool) artifacts.Artifacter {
	//TODO implement me
	panic("implement me")
}

func (l Local) CreateLogger(ctx context.Context, logGroup, logName string) io.Writer {
	//TODO implement me
	panic("implement me")
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
