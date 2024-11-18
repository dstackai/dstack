package repo

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"path"
	"strings"

	"github.com/bluekeyes/go-gitdiff/gitdiff"
	"github.com/dstackai/dstack/runner/internal/log"
)

func ApplyDiff(ctx context.Context, dir, patch string) error {
	// TODO: Critical - avoid applying diff multiple times (e.g. if a job/run is resumed/restarted)
	log.Info(ctx, "apply diff start", "dir", dir)
	files, _, err := gitdiff.Parse(strings.NewReader(patch + "\n"))
	if err != nil {
		return err
	}

	output := &bytes.Buffer{}
	empty := bytes.NewReader([]byte{})

	for _, fileInfo := range files {
		log.Trace(ctx, "apply diff file", "file", fileInfo.OldName, "text_fragments_cnt", len(fileInfo.TextFragments))
		var oldFile *os.File
		output.Reset()
		var input io.ReaderAt = empty
		if fileInfo.OldName != "" {
			oldFile, err = os.Open(path.Join(dir, fileInfo.OldName))
			input = oldFile
			if err != nil {
				log.Error(ctx, "apply diff can not open file", "filename", fileInfo.OldName, "err", err)
				return err
			}
		}
		err = gitdiff.Apply(output, input, fileInfo)
		_ = oldFile.Close()
		if err != nil {
			ae := &gitdiff.ApplyError{}
			var aes string
			if errors.As(err, &ae) {
				aes = fmt.Sprintf("ApplyError{Fragment: %d, FragmentLine: %d, Line: %d}",
					ae.Fragment, ae.FragmentLine, ae.Line)
			}
			log.Error(ctx, "diff applier error", "filename", fileInfo.OldName, "err", err, "ae", aes)
			return err
		}

		if !fileInfo.IsDelete {
			if fileInfo.IsNew || fileInfo.IsRename {
				dd := path.Dir(path.Join(dir, fileInfo.NewName))
				err = os.MkdirAll(dd, 0o755)
				if err != nil {
					log.Warning(ctx, "diff apply new file mkdir fail",
						"filename", fileInfo.NewName,
						"err", err)
				}
			}
			mode := fileModeHeuristic(ctx, dir, fileInfo)
			err = os.WriteFile(path.Join(dir, fileInfo.NewName), output.Bytes(), mode)
			if err != nil {
				log.Error(ctx, "diff apply write file", "filename", fileInfo.NewName, "err", err)
				return err
			}
			// WriteFile does not change perm for existing files
			err = os.Chmod(path.Join(dir, fileInfo.NewName), mode)
			if err != nil {
				log.Warning(ctx, "diff apply can not chmod", "filename", fileInfo.NewName, "err", err)
			}
		}

		if fileInfo.IsDelete || fileInfo.IsRename {
			err = os.Remove(path.Join(dir, fileInfo.OldName))
			if err != nil {
				log.Warning(ctx, "diff apply can not delete", "filename", fileInfo.OldName, "err", err)
			}
		}
	}

	return nil
}

func fileModeHeuristic(ctx context.Context, dir string, fileInfo *gitdiff.File) os.FileMode {
	mode := fileInfo.NewMode
	if mode == 0 {
		mode = fileInfo.OldMode
	}
	if mode == 0 && fileInfo.OldName != "" {
		// diff does not have mode info for rename only cases
		stat, err := os.Stat(path.Join(dir, fileInfo.OldName))
		if err != nil {
			log.Warning(ctx, "diff apply can not stat old file",
				"filename", fileInfo.OldName,
				"err", err)
		} else {
			mode = stat.Mode()
		}
	}
	if mode == 0 {
		mode = 0o644 // fallback to git no-exec default
	}
	return mode
}
