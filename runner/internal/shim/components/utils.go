package components

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/dstackai/dstack/runner/internal/common/log"
	"github.com/dstackai/dstack/runner/internal/common/utils"
)

const (
	downloadTimeout = 10 * time.Minute
	cacheSuffix     = ".cache"
	etagSuffix      = ".etag"
)

// downloadFile ensures that path contains the artifact served at url.
//
// To avoid re-transferring bytes that were already fetched (e.g. when the caller
// repeatedly forces installs of the same artifact), the downloaded bytes are cached
// next to path and revalidated with the object's ETag via a conditional request: an
// unchanged artifact is answered with 304 Not Modified and no body is transferred.
// The cached bytes are then installed to path via chmod+rename; if that finalization
// fails, a later call retries it from the cache without re-downloading. Without
// force, an already-installed path is left untouched (preserving prior behavior).
func downloadFile(ctx context.Context, url string, path string, mode os.FileMode, force bool) error {
	if !force {
		if _, err := os.Stat(path); err == nil {
			log.Debug(ctx, "file exists, skipping download", "path", path)
			return nil
		} else if !os.IsNotExist(err) {
			return fmt.Errorf("check file exists: %w", err)
		}
	}

	cachePath := path + cacheSuffix
	etagPath := path + etagSuffix

	downloaded, err := ensureCached(ctx, url, cachePath, etagPath)
	if err != nil {
		return err
	}

	// If the artifact has not changed and path already matches the cache, there is
	// nothing to do. Otherwise (first install, changed artifact, or a previous
	// finalization that failed) install the cached bytes -- without re-downloading.
	if !downloaded {
		installed, err := sameSize(path, cachePath)
		if err != nil {
			return err
		}
		if installed {
			return nil
		}
	}
	return installFile(ctx, cachePath, path, mode)
}

// ensureCached makes sure cachePath holds the current bytes of the artifact at url,
// transferring the body only if the cached copy is missing or stale (validated with
// the stored ETag). It reports whether a new copy was actually downloaded.
func ensureCached(ctx context.Context, url string, cachePath string, etagPath string) (downloaded bool, err error) {
	ctx, cancel := context.WithTimeout(ctx, downloadTimeout)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return false, fmt.Errorf("create download request: %w", err)
	}
	// Revalidate the cached copy only if we have both the bytes and a validator for them.
	if exists, _ := fileExists(cachePath); exists {
		if etag := readETag(etagPath); etag != "" {
			req.Header.Set("If-None-Match", etag)
		}
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return false, fmt.Errorf("execute download request: %w", err)
	}
	defer func() {
		if cerr := resp.Body.Close(); cerr != nil {
			log.Error(ctx, "downloadFile: close body error", "err", cerr)
		}
	}()

	switch resp.StatusCode {
	case http.StatusNotModified:
		log.Debug(ctx, "cached artifact is up to date, skipping download", "url", url)
		return false, nil
	case http.StatusOK:
		// download below
	default:
		return false, fmt.Errorf("unexpected status code %s downloading from %s", resp.Status, url)
	}

	log.Debug(ctx, "downloading", "url", url, "cache", cachePath)
	written, err := writeAtomic(ctx, cachePath, resp.Body)
	if err != nil {
		return false, err
	}
	log.Debug(ctx, "artifact downloaded", "cache", cachePath, "bytes", written)

	// Store the validator for next time (best effort). If it is missing, the next
	// run simply revalidates with a full GET -- safe, at most one extra download.
	if etag := resp.Header.Get("ETag"); etag != "" {
		if werr := os.WriteFile(etagPath, []byte(etag), 0o644); werr != nil {
			log.Warning(ctx, "failed to store etag", "path", etagPath, "err", werr)
		}
	} else if rerr := os.Remove(etagPath); rerr != nil && !errors.Is(rerr, os.ErrNotExist) {
		log.Warning(ctx, "failed to remove stale etag", "path", etagPath, "err", rerr)
	}
	return true, nil
}

// installFile copies src to dst with the given mode using an atomic rename. It never
// touches the network, so it is safe and cheap to retry.
func installFile(ctx context.Context, src string, dst string, mode os.FileMode) error {
	in, err := os.Open(src)
	if err != nil {
		return fmt.Errorf("open cache %s: %w", src, err)
	}
	defer func() { _ = in.Close() }()

	written, err := writeAtomicMode(ctx, dst, in, mode)
	if err != nil {
		return err
	}
	log.Debug(ctx, "file has been installed", "path", dst, "bytes", written)
	return nil
}

// writeAtomic streams r into dst via a temp file and an atomic rename.
func writeAtomic(ctx context.Context, dst string, r io.Reader) (int64, error) {
	return writeAtomicMode(ctx, dst, r, 0)
}

// writeAtomicMode streams r into dst via a temp file and an atomic rename, applying
// mode before the rename when mode is non-zero.
func writeAtomicMode(ctx context.Context, dst string, r io.Reader, mode os.FileMode) (int64, error) {
	dir, name := filepath.Split(dst)
	tmp, err := os.CreateTemp(dir, fmt.Sprintf(".*-%s", name))
	if err != nil {
		return 0, fmt.Errorf("create temp file for %s: %w", name, err)
	}
	defer cleanupTemp(ctx, tmp)

	written, err := io.Copy(tmp, r)
	if err != nil {
		return written, fmt.Errorf("copy %s: %w", name, err)
	}
	if mode != 0 {
		if err := tmp.Chmod(mode); err != nil {
			return written, fmt.Errorf("chmod %s: %w", dst, err)
		}
	}
	if err := tmp.Close(); err != nil {
		return written, fmt.Errorf("close %s: %w", name, err)
	}
	if err := os.Rename(tmp.Name(), dst); err != nil {
		return written, fmt.Errorf("move %s to %s: %w", name, dst, err)
	}
	return written, nil
}

// cleanupTemp removes a temp file best-effort. After a successful rename the file is
// already gone, so a not-exist error is expected and ignored.
func cleanupTemp(ctx context.Context, f *os.File) {
	_ = f.Close() // best effort; may already be closed
	if err := os.Remove(f.Name()); err != nil && !errors.Is(err, os.ErrNotExist) {
		log.Error(ctx, "remove temp file", "err", err)
	}
}

func fileExists(path string) (bool, error) {
	if _, err := os.Stat(path); err == nil {
		return true, nil
	} else if errors.Is(err, os.ErrNotExist) {
		return false, nil
	} else {
		return false, err
	}
}

func readETag(path string) string {
	data, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(data))
}

// sameSize reports whether both paths exist and have the same size. It is a cheap
// check for whether dst was already installed from the cache (the artifacts are
// content-addressed by version, so a size match is a reliable proxy here).
func sameSize(a string, b string) (bool, error) {
	ai, err := os.Stat(a)
	if errors.Is(err, os.ErrNotExist) {
		return false, nil
	} else if err != nil {
		return false, err
	}
	bi, err := os.Stat(b)
	if err != nil {
		return false, err
	}
	return ai.Size() == bi.Size(), nil
}

func checkDstackComponent(ctx context.Context, name ComponentName, pth string) (status ComponentStatus, version string, err error) {
	exists, err := utils.PathExists(pth)
	if err != nil {
		return ComponentStatusError, "", fmt.Errorf("check %s: %w", name, err)
	}
	if !exists {
		return ComponentStatusNotInstalled, "", nil
	}

	cmd := exec.CommandContext(ctx, pth, "--version")
	output, err := cmd.Output()
	if err != nil {
		return ComponentStatusError, "", fmt.Errorf("check %s: %w", name, err)
	}

	rawVersion := string(output) // dstack-{shim,runner} version 0.19.38
	versionFields := strings.Fields(rawVersion)
	if len(versionFields) != 3 {
		return ComponentStatusError, "", fmt.Errorf("check %s: unexpected version output: %s", name, rawVersion)
	}
	if versionFields[0] != string(name) {
		return ComponentStatusError, "", fmt.Errorf("check %s: unexpected component name: %s", name, versionFields[0])
	}
	return ComponentStatusInstalled, versionFields[2], nil
}
