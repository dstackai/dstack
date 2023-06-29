package base

import (
	"context"

	"github.com/docker/docker/api/types/mount"
)

type Artifacter interface {
	BeforeRun(ctx context.Context) error
	AfterRun(ctx context.Context) error
	DockerBindings(workDir string) ([]mount.Mount, error) // fixme: ./data and /data may conflict
}

type Validator interface {
	Validate(ctx context.Context) error
}
