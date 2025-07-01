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
	if ex.jobSpec.User != nil {
		if ex.jobSpec.User.HomeDir != "" {
			homeDir = ex.jobSpec.User.HomeDir
		}
		if ex.jobSpec.User.Uid != nil {
			uid = int(*ex.jobSpec.User.Uid)
		}
		if ex.jobSpec.User.Gid != nil {
			gid = int(*ex.jobSpec.User.Gid)
		}
	}

	for _, fa := range ex.jobSpec.FileArchives {
		log.Trace(ctx, "Extracting file archive", "id", fa.Id, "path", fa.Path)

		p := path.Clean(fa.Path)
		// `~username[/path/to]` is not supported
		if p == "~" {
			p = homeDir
		} else if rest, found := strings.CutPrefix(p, "~/"); found {
			p = path.Join(homeDir, rest)
		} else if !path.IsAbs(p) {
			p = path.Join(ex.workingDir, p)
		}
		dir, root := path.Split(p)
		if err := mkdirAll(ctx, dir, uid, gid); err != nil {
			return gerrors.Wrap(err)
		}

		if err := os.RemoveAll(p); err != nil {
			log.Warning(ctx, "Failed to remove", "path", p, "err", err)
		}

		archivePath := path.Join(ex.archiveDir, fa.Id)
		archive, err := os.Open(archivePath)
		if err != nil {
			return gerrors.Wrap(err)
		}
		defer func() {
			_ = archive.Close()
			if err := os.Remove(archivePath); err != nil {
				log.Warning(ctx, "Failed to remove archive", "path", archivePath, "err", err)
			}
		}()

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
