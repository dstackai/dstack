package gcp

import (
	"context"
	"errors"
	"os"
	"path"
	"path/filepath"

	"github.com/docker/docker/api/types/mount"
	"github.com/dstackai/dstack/runner/internal/log"
)

type GCPArtifacter struct {
	storage    *GCPStorage
	workDir    string
	pathLocal  string
	pathRemote string
}

func NewGCPArtifacter(storage *GCPStorage, workDir, pathLocal, pathRemote string) *GCPArtifacter {
	err := os.MkdirAll(path.Join(workDir, pathLocal), 0o755)
	if err != nil {
		return nil
	}
	return &GCPArtifacter{
		storage:    storage,
		workDir:    workDir,
		pathLocal:  pathLocal,
		pathRemote: pathRemote,
	}
}

func (gart *GCPArtifacter) BeforeRun(ctx context.Context) error {
	log.Trace(ctx, "Download artifact", "artifact", gart.pathLocal)
	return gart.storage.DownloadDir(ctx, gart.pathRemote, path.Join(gart.workDir, gart.pathLocal))
}

func (gart *GCPArtifacter) AfterRun(ctx context.Context) error {
	log.Trace(ctx, "Upload artifact", "artifact", gart.pathLocal)
	return gart.storage.UploadDir(ctx, path.Join(gart.workDir, gart.pathLocal), gart.pathRemote)
}

func (gart *GCPArtifacter) DockerBindings(workDir string) ([]mount.Mount, error) {
	cleanPath := filepath.Clean(gart.pathLocal)
	if path.IsAbs(cleanPath) && path.Dir(cleanPath) == cleanPath {
		return nil, errors.New("directory needs to be a non-root path")
	}
	dir := gart.pathLocal
	if !filepath.IsAbs(gart.pathLocal) {
		dir = path.Join(workDir, gart.pathLocal)
	}
	return []mount.Mount{
		{
			Type:   mount.TypeBind,
			Source: path.Join(gart.workDir, gart.pathLocal),
			Target: dir,
		},
	}, nil
}
