package simple

import (
	"context"
	"errors"
	"os"
	"path"
	"path/filepath"

	"github.com/docker/docker/api/types/mount"
	"github.com/dstackai/dstack/runner/internal/artifacts"
	"github.com/dstackai/dstack/runner/internal/artifacts/client"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
)

var _ artifacts.Artifacter = (*Simple)(nil)

type Simple struct {
	bucket     string
	workDir    string
	pathLocal  string
	pathRemote string

	doSync   bool
	transfer *client.Copier
}

func (s *Simple) BeforeRun(ctx context.Context) error {
	log.Trace(ctx, "Download artifact", "artifact", s.pathLocal)
	s.transfer.Download(ctx, s.bucket, s.pathRemote, path.Join(s.workDir, s.pathLocal))
	return nil
}

func (s *Simple) AfterRun(ctx context.Context) error {
	log.Trace(ctx, "Upload artifact", "artifact", s.pathLocal)
	var err error = nil
	if s.doSync {
		err = s.transfer.SyncDirUpload(ctx, s.bucket, path.Join(s.workDir, s.pathLocal), s.pathRemote)
	} else {
		s.transfer.Upload(ctx, s.bucket, s.pathRemote, path.Join(s.workDir, s.pathLocal))
	}
	return err
}

func (s *Simple) DockerBindings(workDir string) ([]mount.Mount, error) {
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
			Source: path.Join(s.workDir, s.pathLocal),
			Target: dir,
		},
	}, nil
}

func NewSimple(bucket, region, workDir, pathLocal, pathRemote string, doSync bool) (*Simple, error) {
	s := &Simple{
		bucket:     bucket,
		workDir:    workDir,
		transfer:   client.New(region),
		pathLocal:  pathLocal,
		pathRemote: pathRemote,
		doSync:     doSync,
	}
	dir := path.Join(s.workDir, pathLocal)
	err := os.MkdirAll(dir, 0o755)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return s, nil
}
