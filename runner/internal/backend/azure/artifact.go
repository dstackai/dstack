package azure

import (
	"context"
	"errors"
	"os"
	"path"
	"path/filepath"

	"github.com/docker/docker/api/types/mount"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
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
	log.Trace(ctx, "Upload artifact", "artifact", azartifacter.pathLocal)
	return gerrors.Wrap(azartifacter.storage.UploadDir(ctx, path.Join(azartifacter.workDir, azartifacter.pathLocal), azartifacter.pathRemote))
}

func (azartifacter *AzureArtifacter) DockerBindings(workDir string) ([]mount.Mount, error) {
	cleanPath := filepath.Clean(azartifacter.pathLocal)
	if path.IsAbs(cleanPath) && path.Dir(cleanPath) == cleanPath {
		return nil, errors.New("directory needs to be a non-root path")
	}
	dir := azartifacter.pathLocal
	if !filepath.IsAbs(azartifacter.pathLocal) {
		dir = path.Join(workDir, azartifacter.pathLocal)
	}
	return []mount.Mount{
		{
			Type:   mount.TypeBind,
			Source: path.Join(azartifacter.workDir, azartifacter.pathLocal),
			Target: dir,
		},
	}, nil
}
