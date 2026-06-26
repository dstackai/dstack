package components

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/dstackai/dstack/runner/internal/common/log"
	"github.com/dstackai/dstack/runner/internal/common/utils"
)

const (
	downloadTimeout = 10 * time.Minute
	cacheSuffix     = ".cache"
	etagSuffix      = ".etag"
	// Max per-version caches kept next to a binary (bounds disk use).
	maxCachedVersions = 5
)

// downloadFile ensures path holds the artifact at url.
//
// Bytes are cached next to path (one cache per URL, validated by ETag), so a repeated
// or forced install of an unchanged version returns 304 and transfers nothing. Cached
// bytes are then chmod+renamed into place; a failed rename retries from cache without
// re-downloading. With force=false an existing path is left as-is.
func downloadFile(ctx context.Context, url string, path string, mode os.FileMode, force bool) error {
	if !force {
		if _, err := os.Stat(path); err == nil {
			log.Debug(ctx, "file exists, skipping download", "path", path)
			return nil
		} else if !os.IsNotExist(err) {
			return fmt.Errorf("check file exists: %w", err)
		}
	}

	// One cache file per URL so several versions can coexist. With a single shared
	// cache, a request for a different version would overwrite it and force a
	// re-download every time the requested version changes.
	key := urlKey(url)
	cachePath := fmt.Sprintf("%s.%s%s", path, key, cacheSuffix)
	etagPath := fmt.Sprintf("%s.%s%s", path, key, etagSuffix)

	downloaded, err := ensureCached(ctx, url, cachePath, etagPath)
	if err != nil {
		return err
	}
	if downloaded {
		pruneCaches(ctx, path, maxCachedVersions)
	}

	// Install the cached bytes; skip if path already matches the cache.
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

// ensureCached makes cachePath hold url's current bytes, downloading only if the cache
// is missing or stale (per the stored ETag). Reports whether it downloaded.
func ensureCached(ctx context.Context, url string, cachePath string, etagPath string) (downloaded bool, err error) {
	ctx, cancel := context.WithTimeout(ctx, downloadTimeout)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return false, fmt.Errorf("create download request: %w", err)
	}
	// Revalidate only if we have both cached bytes and an ETag for them.
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
		// fall through to download
	default:
		return false, fmt.Errorf("unexpected status code %s downloading from %s", resp.Status, url)
	}

	log.Debug(ctx, "downloading", "path", cachePath, "url", url)
	written, err := writeAtomic(ctx, cachePath, resp.Body)
	if err != nil {
		return false, err
	}
	log.Debug(ctx, "file has been downloaded", "path", cachePath, "bytes", written)

	// Remember the ETag for next time (best effort; if absent, next run does a full GET).
	if etag := resp.Header.Get("ETag"); etag != "" {
		if werr := os.WriteFile(etagPath, []byte(etag), 0o644); werr != nil {
			log.Warning(ctx, "failed to store etag", "path", etagPath, "err", werr)
		}
	} else if rerr := os.Remove(etagPath); rerr != nil && !errors.Is(rerr, os.ErrNotExist) {
		log.Warning(ctx, "failed to remove stale etag", "path", etagPath, "err", rerr)
	}
	return true, nil
}

// installFile copies src to dst (with mode) via an atomic rename. No network, safe to retry.
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

// writeAtomicMode streams r into dst via a temp file and an atomic rename, setting the
// file mode (when non-zero) before the rename.
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

// cleanupTemp best-effort removes the temp file (already gone after a successful rename).
func cleanupTemp(ctx context.Context, f *os.File) {
	_ = f.Close() // may already be closed
	if err := os.Remove(f.Name()); err != nil && !errors.Is(err, os.ErrNotExist) {
		log.Error(ctx, "remove temp file", "err", err)
	}
}

// pruneCaches keeps the `keep` newest per-version caches next to path (and their .etag),
// removing the rest.
func pruneCaches(ctx context.Context, path string, keep int) {
	matches, err := filepath.Glob(path + ".*" + cacheSuffix)
	if err != nil || len(matches) <= keep {
		return
	}
	type cacheFile struct {
		name string
		mod  time.Time
	}
	files := make([]cacheFile, 0, len(matches))
	for _, m := range matches {
		fi, err := os.Stat(m)
		if err != nil {
			continue
		}
		files = append(files, cacheFile{m, fi.ModTime()})
	}
	if len(files) <= keep {
		return
	}
	sort.Slice(files, func(i, j int) bool { return files[i].mod.After(files[j].mod) })
	for _, f := range files[keep:] {
		if err := os.Remove(f.name); err != nil && !errors.Is(err, os.ErrNotExist) {
			log.Warning(ctx, "prune cache: remove", "path", f.name, "err", err)
		}
		etag := strings.TrimSuffix(f.name, cacheSuffix) + etagSuffix
		if err := os.Remove(etag); err != nil && !errors.Is(err, os.ErrNotExist) {
			log.Warning(ctx, "prune cache: remove etag", "path", etag, "err", err)
		}
	}
}

// urlKey returns a short, filesystem-safe key derived from url, used to name its cache file.
func urlKey(url string) string {
	sum := sha256.Sum256([]byte(url))
	return hex.EncodeToString(sum[:])[:16]
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

// sameSize reports whether a and b both exist with the same size -- a cheap "is path
// already this cached binary?" check (different versions differ in size).
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
