package executor

import (
	"context"
	"github.com/dstackai/dstack/runner/internal/log"
)

type SecretsInterpolator struct {
	Secrets map[string]string
}

func (si *SecretsInterpolator) interpolate(ctx context.Context, value string) string {
	log.Trace(ctx, "Interpolating", "val", value)
	return value // todo
}
