package executor

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"path"
	"regexp"
	"slices"
	"strings"

	"github.com/codeclysm/extract/v4"
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
func (ex *RunExecutor) setupFiles(ctx context.Context) error {
	homeDir := ex.workingDir
	uid := -1
	gid := -1
	// User must be already set
	if ex.jobSpec.User.HomeDir != "" {
		homeDir = ex.jobSpec.User.HomeDir
	}
	if ex.jobSpec.User.Uid != nil {
		uid = int(*ex.jobSpec.User.Uid)
	}
	if ex.jobSpec.User.Gid != nil {
		gid = int(*ex.jobSpec.User.Gid)
	}

	for _, fa := range ex.jobSpec.FileArchives {
		archivePath := path.Join(ex.archiveDir, fa.Id)
		if err := extractFileArchive(ctx, archivePath, fa.Path, ex.workingDir, uid, gid, homeDir); err != nil {
			return gerrors.Wrap(err)
		}
	}

	if err := os.RemoveAll(ex.archiveDir); err != nil {
		log.Warning(ctx, "Failed to remove file archives dir", "path", ex.archiveDir, "err", err)
	}

	return nil
}

func extractFileArchive(ctx context.Context, archivePath string, targetPath string, targetRoot string, uid int, gid int, homeDir string) error {
	log.Trace(ctx, "Extracting file archive", "archive", archivePath, "target", targetPath)

	targetPath = path.Clean(targetPath)
	// `~username[/path/to]` is not supported
	if targetPath == "~" {
		targetPath = homeDir
	} else if rest, found := strings.CutPrefix(targetPath, "~/"); found {
		targetPath = path.Join(homeDir, rest)
	} else if !path.IsAbs(targetPath) {
		targetPath = path.Join(targetRoot, targetPath)
	}
	dir, root := path.Split(targetPath)
	if err := mkdirAll(ctx, dir, uid, gid); err != nil {
		return gerrors.Wrap(err)
	}
	if err := os.RemoveAll(targetPath); err != nil {
		log.Warning(ctx, "Failed to remove", "path", targetPath, "err", err)
	}

	archive, err := os.Open(archivePath)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer archive.Close()

	var paths []string
	repl := fmt.Sprintf("%s$2", root)
	renameAndRemember := func(s string) string {
		s = renameRegex.ReplaceAllString(s, repl)
		paths = append(paths, s)
		return s
	}
	if err := extract.Tar(ctx, archive, dir, renameAndRemember); err != nil {
		return gerrors.Wrap(err)
	}

	if uid != -1 || gid != -1 {
		for _, p := range paths {
			if err := os.Chown(path.Join(dir, p), uid, gid); err != nil {
				log.Warning(ctx, "Failed to chown", "path", p, "err", err)
			}
		}
	}

	return nil
}

func mkdirAll(ctx context.Context, p string, uid int, gid int) error {
	var paths []string
	for {
		p = path.Dir(p)
		if p == "/" {
			break
		}
		paths = append(paths, p)
	}
	for _, p := range slices.Backward(paths) {
		if _, err := os.Stat(p); errors.Is(err, os.ErrNotExist) {
			if err := os.Mkdir(p, 0o755); err != nil {
				return err
			}
			if err := os.Chown(p, uid, gid); err != nil {
				log.Warning(ctx, "Failed to chown", "path", p, "err", err)
			}
		} else if err != nil {
			return err
		}
	}
	return nil
}
