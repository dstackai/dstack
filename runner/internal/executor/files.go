package executor

import (
	"context"
	"fmt"
	"io"
	"os"
	"path"
	"regexp"

	"github.com/codeclysm/extract/v4"
	"github.com/dstackai/dstack/runner/internal/common"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
)

var renameRegex = regexp.MustCompile(`^([^/]*)(/|$)`)

func (ex *RunExecutor) AddFileArchive(id string, src io.Reader) error {
	if err := os.MkdirAll(ex.archiveDir, 0o755); err != nil {
		return gerrors.Wrap(err)
	}
	archivePath := path.Join(ex.archiveDir, id)
	archive, err := os.Create(archivePath)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = archive.Close() }()
	if _, err = io.Copy(archive, src); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

// setupFiles must be called from Run
// ex.jobWorkingDir must be already created
func (ex *RunExecutor) setupFiles(ctx context.Context) error {
	for _, fa := range ex.jobSpec.FileArchives {
		archivePath := path.Join(ex.archiveDir, fa.Id)
		if err := extractFileArchive(ctx, archivePath, fa.Path, ex.jobWorkingDir, ex.jobUid, ex.jobGid, ex.jobHomeDir); err != nil {
			return gerrors.Wrap(err)
		}
	}

	if err := os.RemoveAll(ex.archiveDir); err != nil {
		log.Warning(ctx, "Failed to remove file archives dir", "path", ex.archiveDir, "err", err)
	}

	return nil
}

func extractFileArchive(ctx context.Context, archivePath string, destPath string, baseDir string, uid int, gid int, homeDir string) error {
	log.Trace(ctx, "Extracting file archive", "archive", archivePath, "dest", destPath, "base", baseDir, "home", homeDir)

	destPath, err := common.ExpandPath(destPath, baseDir, homeDir)
	if err != nil {
		return gerrors.Wrap(err)
	}
	destBase, destName := path.Split(destPath)
	if err := common.MkdirAll(ctx, destBase, uid, gid); err != nil {
		return gerrors.Wrap(err)
	}
	if err := os.RemoveAll(destPath); err != nil {
		log.Warning(ctx, "Failed to remove", "path", destPath, "err", err)
	}

	archive, err := os.Open(archivePath)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer archive.Close()

	var paths []string
	repl := fmt.Sprintf("%s$2", destName)
	renameAndRemember := func(s string) string {
		s = renameRegex.ReplaceAllString(s, repl)
		paths = append(paths, s)
		return s
	}
	if err := extract.Tar(ctx, archive, destBase, renameAndRemember); err != nil {
		return gerrors.Wrap(err)
	}

	if uid != -1 || gid != -1 {
		for _, p := range paths {
			log.Warning(ctx, "path", "path", p)
			if err := os.Chown(path.Join(destBase, p), uid, gid); err != nil {
				log.Warning(ctx, "Failed to chown", "path", p, "err", err)
			}
		}
	}

	return nil
}
