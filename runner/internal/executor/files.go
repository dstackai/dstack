package executor

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"path"
	"path/filepath"
	"regexp"

	"github.com/codeclysm/extract/v4"

	"github.com/dstackai/dstack/runner/internal/common"
	"github.com/dstackai/dstack/runner/internal/log"
)

var renameRegex = regexp.MustCompile(`^([^/]*)(/|$)`)

func (ex *RunExecutor) AddFileArchive(id string, src io.Reader) error {
	if err := os.MkdirAll(ex.archiveDir, 0o755); err != nil {
		return fmt.Errorf("create archive directory: %w", err)
	}
	archivePath := path.Join(ex.archiveDir, id)
	archive, err := os.Create(archivePath)
	if err != nil {
		return fmt.Errorf("create archive file: %w", err)
	}
	defer func() { _ = archive.Close() }()
	if _, err = io.Copy(archive, src); err != nil {
		return fmt.Errorf("copy archive data: %w", err)
	}
	return nil
}

// setupFiles must be called from Run
// Must be called after setJobWorkingDir and setJobCredentials
func (ex *RunExecutor) setupFiles(ctx context.Context) error {
	log.Trace(ctx, "Setting up files")
	if ex.jobWorkingDir == "" {
		return errors.New("setup files: working dir is not set")
	}
	if !filepath.IsAbs(ex.jobWorkingDir) {
		return fmt.Errorf("setup files: working dir must be absolute: %s", ex.jobWorkingDir)
	}
	for _, fa := range ex.jobSpec.FileArchives {
		archivePath := path.Join(ex.archiveDir, fa.Id)
		if err := extractFileArchive(ctx, archivePath, fa.Path, ex.jobWorkingDir, ex.jobUid, ex.jobGid, ex.jobHomeDir); err != nil {
			return fmt.Errorf("extract file archive %s: %w", fa.Id, err)
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
		return fmt.Errorf("expand destination path: %w", err)
	}
	destBase, destName := path.Split(destPath)
	if err := common.MkdirAll(ctx, destBase, uid, gid); err != nil {
		return fmt.Errorf("create destination directory: %w", err)
	}
	if err := os.RemoveAll(destPath); err != nil {
		log.Warning(ctx, "Failed to remove", "path", destPath, "err", err)
	}

	archive, err := os.Open(archivePath)
	if err != nil {
		return fmt.Errorf("open archive file: %w", err)
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
		return fmt.Errorf("extract tar archive: %w", err)
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
