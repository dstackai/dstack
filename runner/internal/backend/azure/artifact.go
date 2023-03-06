package azure

import (
	"context"
	"github.com/docker/docker/api/types/mount"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"os"
	"path"
)

type AzureArtifacter struct {
	storage    AzureStorage
	workDir    string
	pathLocal  string
	pathRemote string
}

func NewAzureArtifacter(storage AzureStorage, workDir, pathLocal, pathRemote string) *AzureArtifacter {
	err := os.MkdirAll(path.Join(workDir, pathLocal), 0o755)
	if err != nil {
		// XXX: is it better to report failure about making dirs?
		return nil
	}
	return &AzureArtifacter{
		storage:    storage,
		workDir:    workDir,
		pathLocal:  pathLocal,
		pathRemote: pathRemote,
	}
}

func (azartifacter *AzureArtifacter) BeforeRun(ctx context.Context) error {
	log.Trace(ctx, "Download artifact", "artifact", azartifacter.pathLocal)
	return gerrors.Wrap(azartifacter.storage.DownloadDir(ctx, azartifacter.pathRemote, path.Join(azartifacter.workDir, azartifacter.pathLocal)))
}

func (azartifacter *AzureArtifacter) AfterRun(ctx context.Context) error {
	//TODO implement me
	panic("implement me")
}

func (azartifacter *AzureArtifacter) DockerBindings(workDir string) ([]mount.Mount, error) {
	//TODO implement me
	panic("implement me")
}
