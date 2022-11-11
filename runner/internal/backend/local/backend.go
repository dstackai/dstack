package local

import (
	"context"
	"fmt"
	"io"
	"io/ioutil"

	"github.com/dstackai/dstackai/runner/internal/artifacts"
	"github.com/dstackai/dstackai/runner/internal/backend"
	"github.com/dstackai/dstackai/runner/internal/models"
	"gopkg.in/yaml.v3"
)

var _ backend.Backend = (*Local)(nil)

type Local struct {
	path      string
	state     *models.State
	artifacts []artifacts.Artifacter
}

func (l Local) GetJobByPath(_ context.Context, _ string) (*models.Job, error) {
	//TODO implement me
	panic("implement me")
}

func (l Local) GitCredentials(_ context.Context) *models.GitCredentials {
	//TODO implement me
	panic("implement me")
}

func (l Local) Secrets(_ context.Context) (map[string]string, error) {
	//TODO implement me
	panic("implement me")
}

func (l Local) Bucket(_ context.Context) string {
	panic("implement me")
}

func (l Local) ListSubDir(_ context.Context, _ string) ([]string, error) {
	//TODO implement me
	panic("implement me")
}

func (l Local) Init(_ context.Context, _ string) error {
	//TODO implement me
	panic("implement me")
}

func (l Local) Job(_ context.Context) *models.Job {
	//TODO implement me
	panic("implement me")
}

func (l Local) MasterJob(_ context.Context) *models.Job {
	//TODO implement me
	panic("implement me")
}

func (l Local) Requirements(_ context.Context) models.Requirements {
	//TODO implement me
	panic("implement me")
}

func (l Local) UpdateState(_ context.Context) error {
	//TODO implement me
	panic("implement me")
}

func (l Local) CheckStop(_ context.Context) (bool, error) {
	//TODO implement me
	panic("implement me")
}

func (l Local) Shutdown(_ context.Context) error {
	//TODO implement me
	panic("implement me")
}

func (l Local) GetArtifact(_ context.Context, _, _, _ string, _ bool) artifacts.Artifacter {
	//TODO implement me
	panic("implement me")
}

func (l Local) CreateLogger(_ context.Context, _, _ string) io.Writer {
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
