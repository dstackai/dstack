package common

import (
	"context"
	"fmt"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"io/fs"
	"path/filepath"
	"strings"
	"time"
)

type FileInfo struct {
	Size     int64
	Modified time.Time
}

type ObjectInfo struct {
	Key string
	FileInfo
}

type objectOp func(context.Context, string, FileInfo) error

// SyncDirUpload cost-efficiently synchronizes local files tree and objects in remote storage.
// `srcDir` must have trailing slash.
func SyncDirUpload(ctx context.Context, srcDir string, dstObjects chan ObjectInfo, deleteObject objectOp, uploadObject objectOp) error {
	// Optimization: avoid keeping entire tree in memory
	/* Collect local files */
	objectsToUpload := map[string]FileInfo{}
	if err := filepath.Walk(srcDir, func(filepath string, info fs.FileInfo, err error) error {
		if err != nil {
			return nil
		}
		if info.IsDir() {
			return nil
		}
		key := strings.TrimPrefix(filepath, srcDir)
		objectsToUpload[key] = FileInfo{info.Size(), info.ModTime().UTC()}
		return nil
	}); err != nil {
		return gerrors.Wrap(err)
	}
	/* Compare with stored objects */
	for dstInfo := range dstObjects {
		srcInfo, ok := objectsToUpload[dstInfo.Key]
		if !ok {
			log.Trace(ctx, "File doesn't exist anymore", "Key", dstInfo.Key)
			if err := deleteObject(ctx, dstInfo.Key, dstInfo.FileInfo); err != nil {
				log.Warning(ctx, "Failed to delete object", "Key", dstInfo.Key, "err", err)
			}
		} else if dstInfo.Size == srcInfo.Size && dstInfo.Modified == srcInfo.Modified {
			// This won't work with multiple sync uploads. Need to use metadata
			log.Trace(ctx, "Object metadata is the same", "Key", dstInfo.Key)
			delete(objectsToUpload, dstInfo.Key)
		} else {
			log.Trace(ctx, "Object metadata has changed", "Key", dstInfo.Key, "Size l/r", fmt.Sprintf("%dB/%dB", srcInfo.Size, dstInfo.Size), "Updated l/r", fmt.Sprintf("%s/%s", srcInfo.Modified, dstInfo.Modified))
		}
	}
	/* Upload files */
	// todo make parallel
	for key, info := range objectsToUpload {
		if err := uploadObject(ctx, key, info); err != nil {
			log.Warning(ctx, "Failed to upload file", "Key", key, "err", err)
		}
	}
	return nil
}
