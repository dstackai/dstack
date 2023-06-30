package aws

import (
	"context"
	"github.com/docker/docker/api/types/mount"
	"github.com/dstackai/dstack/runner/internal/backend/base"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"os"
	"path"
	"path/filepath"
)

type AWSArtifacter struct {
	storage    *AWSStorage
	workDir    string
	pathLocal  string
	pathRemote string
	doSync     bool
}

func NewAWSArtifacter(storage *AWSStorage, workDir, pathLocal, pathRemote string, doSync bool) (*AWSArtifacter, error) {
	err := os.MkdirAll(path.Join(workDir, pathLocal), 0o755)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return &AWSArtifacter{
		storage:    storage,
		workDir:    workDir,
		pathLocal:  pathLocal,
		pathRemote: pathRemote,
		doSync:     doSync,
	}, nil
}

func (a *AWSArtifacter) BeforeRun(ctx context.Context) error {
	log.Trace(ctx, "Download artifact", "artifact", a.pathLocal)
	return gerrors.Wrap(base.DownloadDir(ctx, a.storage, a.pathRemote, path.Join(a.workDir, a.pathLocal)))
}

func (a *AWSArtifacter) AfterRun(ctx context.Context) error {
	log.Trace(ctx, "Upload artifact", "artifact", a.pathLocal)
	return gerrors.Wrap(base.UploadDir(ctx, a.storage, path.Join(a.workDir, a.pathLocal), a.pathRemote, a.doSync, !a.doSync))
}

func (a *AWSArtifacter) DockerBindings(workDir string) ([]mount.Mount, error) {
	cleanPath := filepath.Clean(a.pathLocal)
	if path.IsAbs(cleanPath) && path.Dir(cleanPath) == cleanPath {
		return nil, gerrors.New("directory needs to be a non-root path")
	}
	dir := a.pathLocal
	if !filepath.IsAbs(a.pathLocal) {
		dir = path.Join(workDir, a.pathLocal)
	}
	return []mount.Mount{
		{
			Type:   mount.TypeBind,
			Source: path.Join(a.workDir, a.pathLocal),
			Target: dir,
		},
	}, nil
}
