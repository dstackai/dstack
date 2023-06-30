package local

import (
	"context"
	"errors"
	"github.com/dstackai/dstack/runner/internal/backend/base"
	"os"
	"path"
	"path/filepath"

	"github.com/docker/docker/api/types/mount"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
)

var _ base.Artifacter = (*LocalArtifacter)(nil)

type LocalArtifacter struct {
	path       string
	workDir    string
	pathLocal  string
	pathRemote string
}

func (s *LocalArtifacter) BeforeRun(ctx context.Context) error {
	return nil
}

func (s *LocalArtifacter) AfterRun(ctx context.Context) error {
	log.Trace(ctx, "Upload artifact", "artifact", s.pathLocal)
	return nil
}

func (s *LocalArtifacter) DockerBindings(workDir string) ([]mount.Mount, error) {
	cleanPath := filepath.Clean(s.pathLocal)
	if path.IsAbs(cleanPath) && path.Dir(cleanPath) == cleanPath {
		return nil, errors.New("directory needs to be a non-root path")
	}
	dir := s.pathLocal
	if !filepath.IsAbs(s.pathLocal) {
		dir = path.Join(workDir, s.pathLocal)
	}

	return []mount.Mount{
		{
			Type:   mount.TypeBind,
			Source: path.Join(s.path, s.pathRemote),
			Target: dir,
		},
	}, nil
}

func NewLocalArtifacter(pathRoot, workDir, pathLocal, pathRemote string) (*LocalArtifacter, error) {
	s := &LocalArtifacter{
		path:       pathRoot,
		workDir:    workDir,
		pathLocal:  pathLocal,
		pathRemote: pathRemote,
	}
	dir := path.Join(s.path, s.pathRemote)

	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, gerrors.Wrap(err)
	}
	return s, nil
}
