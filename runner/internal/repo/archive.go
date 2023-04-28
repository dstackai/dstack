package repo

import (
	"context"
	"github.com/codeclysm/extract/v3"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"os"
)

func ExtractArchive(ctx context.Context, src, dst string) error {
	file, err := os.Open(src)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer file.Close()
	log.Trace(ctx, "Extracting archive", "src", src, "dst", dst)
	if err := extract.Archive(ctx, file, dst, nil); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}
