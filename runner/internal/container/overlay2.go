package container

import (
	"archive/tar"
	"context"
	"encoding/json"
	docker "github.com/docker/docker/client"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/opencontainers/go-digest"
	"io"
	"io/fs"
	"os"
	"path/filepath"
)

const (
	DockerRoot            = "/var/lib/docker"
	DockerImagedbContent  = "image/overlay2/imagedb/content/sha256"
	DockerImagedbMetadata = "image/overlay2/imagedb/metadata/sha256"
	DockerLayerdb         = "image/overlay2/layerdb/sha256"
	DockerOverlay2        = "overlay2"
)

type ImageTag struct {
	Name   string `json:"name"`
	Digest string `json:"digest"`
}
type Writer tar.Writer

// Overlay2ExportImageDiff works directly with docker overlay2 directory to export single layer
// `imageName` must contain tag
func Overlay2ExportImageDiff(ctx context.Context, client docker.APIClient, imageName, diffPath string) error {
	log.Trace(ctx, "Inspect image before export", "name", imageName)
	inspect, _, err := client.ImageInspectWithRaw(ctx, imageName)
	if err != nil {
		return gerrors.Wrap(err)
	}
	imageDigest, err := digest.Parse(inspect.ID)
	if err != nil {
		return gerrors.Wrap(err)
	}
	chainDigest, err := digest.Parse(chainID(inspect.RootFS.Layers))
	if err != nil {
		return gerrors.Wrap(err)
	}
	log.Trace(ctx, "Export image", "ID", imageDigest.Encoded(), "chainID", chainDigest.Encoded())

	cacheIDFile, err := os.Open(filepath.Join(DockerRoot, DockerLayerdb, chainDigest.Encoded(), "cache-id"))
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = cacheIDFile.Close() }()
	cacheIDBytes, err := io.ReadAll(cacheIDFile)
	if err != nil {
		return gerrors.Wrap(err)
	}
	cacheID := string(cacheIDBytes)
	log.Trace(ctx, "Export layer", "cacheID", cacheID)

	imageTagBytes, err := json.Marshal(&ImageTag{
		Name:   imageName,
		Digest: imageDigest.String(),
	})
	if err != nil {
		return gerrors.Wrap(err)
	}

	log.Trace(ctx, "Writing diff tarball", "path", diffPath)
	diffFile, err := os.Create(diffPath)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = diffFile.Close() }()
	diffWriter := tar.NewWriter(diffFile)
	defer func() { _ = diffWriter.Close() }()

	tempFile, err := os.CreateTemp("", "")
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = os.Remove(tempFile.Name()) }()
	tempInfo, err := tempFile.Stat()
	if err != nil {
		return gerrors.Wrap(err)
	}
	imageTagHeader, err := tar.FileInfoHeader(tempInfo, "")
	if err != nil {
		return gerrors.Wrap(err)
	}
	imageTagHeader.Name = "tag.json"
	imageTagHeader.Size = int64(len(imageTagBytes))
	if err := diffWriter.WriteHeader(imageTagHeader); err != nil {
		return gerrors.Wrap(err)
	}
	if _, err := diffWriter.Write(imageTagBytes); err != nil {
		return gerrors.Wrap(err)
	}

	if err := tarWriteFile(diffWriter, filepath.Join(DockerRoot, DockerImagedbContent, imageDigest.Encoded()), DockerRoot); err != nil {
		return gerrors.Wrap(err)
	}
	if err := tarWriteWalk(diffWriter, filepath.Join(DockerRoot, DockerImagedbMetadata, imageDigest.Encoded()), DockerRoot); err != nil {
		return gerrors.Wrap(err)
	}
	if err := tarWriteWalk(diffWriter, filepath.Join(DockerRoot, DockerLayerdb, chainDigest.Encoded()), DockerRoot); err != nil {
		return gerrors.Wrap(err)
	}
	cacheEntries, err := os.ReadDir(filepath.Join(DockerRoot, DockerOverlay2, cacheID))
	if err != nil {
		return gerrors.Wrap(err)
	}
	for _, entry := range cacheEntries {
		if entry.Name() == "work" || entry.Name() == "merged" {
			continue
		}
		if err := tarWriteWalk(diffWriter, filepath.Join(DockerRoot, DockerOverlay2, cacheID, entry.Name()), DockerRoot); err != nil {
			return gerrors.Wrap(err)
		}
	}
	return nil
}

func Overlay2ImportImageDiff(ctx context.Context, diffPath string) error {
	return gerrors.New("not implemented")
}

func chainID(layers []string) string {
	id := layers[0]
	for _, layer := range layers[1:] {
		id = digest.FromString(id + " " + layer).String()
	}
	return id
}

func tarWriteFile(writer *tar.Writer, path string, relTo string) error {
	info, err := os.Stat(path)
	if err != nil {
		return gerrors.Wrap(err)
	}
	if err := tarWritePath(writer, path, info, relTo); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func tarWriteWalk(writer *tar.Writer, root string, relTo string) error {
	if err := filepath.Walk(root, func(path string, info fs.FileInfo, err error) error {
		if err != nil {
			return gerrors.Wrap(err)
		}
		if err := tarWritePath(writer, path, info, relTo); err != nil {
			return gerrors.Wrap(err)
		}
		return nil
	}); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func tarWritePath(writer *tar.Writer, path string, info os.FileInfo, relTo string) error {
	header, err := tar.FileInfoHeader(info, path)
	if err != nil {
		return gerrors.Wrap(err)
	}
	name, err := filepath.Rel(relTo, path)
	if err != nil {
		return gerrors.Wrap(err)
	}
	header.Name = filepath.ToSlash(name)
	if err := writer.WriteHeader(header); err != nil {
		return gerrors.Wrap(err)
	}

	if !info.IsDir() {
		file, err := os.Open(path)
		if err != nil {
			return gerrors.Wrap(err)
		}
		defer func() { _ = file.Close() }()
		if _, err := io.Copy(writer, file); err != nil {
			return gerrors.Wrap(err)
		}
	}
	return nil
}
