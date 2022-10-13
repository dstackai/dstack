package artifacts

import (
	"context"

	"github.com/docker/docker/api/types/mount"
)

type Artifacter interface {
	//Register(pathLocal, pathRemote string) error
	BeforeRun(ctx context.Context) error
	AfterRun(ctx context.Context) error
	DockerBindings(workDir string) []mount.Mount
}

type Validator interface {
	Validate(ctx context.Context) error
}
