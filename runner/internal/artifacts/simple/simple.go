package simple

import (
	"context"
	"os"
	"path"

	"github.com/docker/docker/api/types/mount"
	"github.com/dstackai/dstackai/runner/internal/artifacts"
	"github.com/dstackai/dstackai/runner/internal/artifacts/client"
	"github.com/dstackai/dstackai/runner/internal/gerrors"
	"github.com/dstackai/dstackai/runner/internal/log"
)

var _ artifacts.Artifacter = (*Simple)(nil)

type Simple struct {
	bucket     string
	workDir    string
	pathLocal  string
	pathRemote string

	transfer *client.Copier
}

func (s *Simple) BeforeRun(ctx context.Context) error {
	s.transfer.Download(ctx, s.bucket, s.pathRemote, path.Join(s.workDir, s.pathLocal))
	return nil
}

func (s *Simple) AfterRun(ctx context.Context) error {
	log.Trace(ctx, "Upload artifact", "artifact", s.pathLocal)
	s.transfer.Upload(ctx, s.bucket, s.pathRemote, path.Join(s.workDir, s.pathLocal))
	return nil
}

func (s *Simple) DockerBindings(workDir string) []mount.Mount {
	return []mount.Mount{
		{
			Type:   mount.TypeBind,
			Source: path.Join(s.workDir, s.pathLocal),
			Target: path.Join(workDir, s.pathLocal),
		},
	}
}

func NewSimple(bucket, region, workDir, pathLocal, pathRemote string) (*Simple, error) {
	s := &Simple{
		bucket:     bucket,
		workDir:    workDir,
		transfer:   client.New(region),
		pathLocal:  pathLocal,
		pathRemote: pathRemote,
	}
	dir := path.Join(s.workDir, pathLocal)
	err := os.MkdirAll(dir, 0o755)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return s, nil
}
