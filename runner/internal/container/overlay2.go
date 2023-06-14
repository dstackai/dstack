package container

import (
	"archive/tar"
	"context"
	"encoding/json"
	"fmt"
	"github.com/codeclysm/extract/v3"
	docker "github.com/docker/docker/client"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/opencontainers/go-digest"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
)

const (
	DockerRoot            = "/var/lib/docker"
	DockerRepositories    = "image/overlay2/repositories.json"
	DockerImagedbContent  = "image/overlay2/imagedb/content/sha256"
	DockerImagedbMetadata = "image/overlay2/imagedb/metadata/sha256"
	DockerLayerdb         = "image/overlay2/layerdb/sha256"
	DockerOverlay2        = "overlay2"
)

type ImageTag struct {
	Name   string `json:"name"`
	Digest string `json:"digest"`
}

type Repositories struct {
	Repositories map[string]map[string]string `json:"Repositories"`
}

type ImageManifest struct {
	RootFS struct {
		Layers []string `json:"diff_ids"`
	} `json:"rootfs"`
}

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
	log.Trace(ctx, "Export image", "ID", imageDigest.Encoded(), "chainID", getChainID(inspect.RootFS.Layers))

	chainDigest, err := digest.Parse(getChainID(inspect.RootFS.Layers))
	if err != nil {
		return gerrors.Wrap(err)
	}
	cacheID, err := getCacheID(chainDigest.String())
	if err != nil {
		return gerrors.Wrap(err)
	}
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
		if entry.Name() == "link" {
			link, err := getCacheLink(cacheID)
			if err != nil {
				return gerrors.Wrap(err)
			}
			if err := tarWriteFile(diffWriter, filepath.Join(DockerRoot, DockerOverlay2, "l", link), DockerRoot); err != nil {
				return gerrors.Wrap(err)
			}
		}
	}
	return nil
}

func Overlay2ImportImageDiff(ctx context.Context, diffPath string) error {
	log.Trace(ctx, "Opening archive to import image diff", "path", diffPath)
	diffFile, err := os.Open(diffPath)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = diffFile.Close() }()

	log.Trace(ctx, "Extracting image diff from archive")
	imageTag, err := extractImageTag(diffPath)
	if err != nil {
		return gerrors.Wrap(err)
	}
	err = extract.Archive(ctx, diffFile, DockerRoot, func(path string) string {
		if path == "tag.json" {
			return ""
		}
		return path
	})
	if err != nil {
		return gerrors.Wrap(err)
	}

	var repos Repositories
	reposBytes, err := os.ReadFile(filepath.Join(DockerRoot, DockerRepositories))
	if err != nil {
		return gerrors.Wrap(err)
	}
	if err := json.Unmarshal(reposBytes, &repos); err != nil {
		return gerrors.Wrap(err)
	}

	if _, ok := repos.Repositories[imageTag.Repo()]; !ok {
		repos.Repositories[imageTag.Repo()] = make(map[string]string)
	}
	repoTags, _ := repos.Repositories[imageTag.Repo()]
	repoTags[imageTag.Name] = imageTag.Digest
	reposBytes, err = json.Marshal(repos)
	if err != nil {
		return gerrors.Wrap(err)
	}
	if err := os.WriteFile(filepath.Join(DockerRoot, DockerRepositories), reposBytes, 0644); err != nil {
		return gerrors.Wrap(err)
	}

	log.Trace(ctx, "Rebuilding lower links")
	imageManifest, err := getImageManifest(imageTag.Digest)
	if err != nil {
		return gerrors.Wrap(err)
	}
	links := make([]string, 0)
	for i := 1; i < len(imageManifest.RootFS.Layers); i++ {
		cacheID, err := getCacheID(getChainID(imageManifest.RootFS.Layers[:i]))
		if err != nil {
			return gerrors.Wrap(err)
		}
		link, err := getCacheLink(cacheID)
		if err != nil {
			return gerrors.Wrap(err)
		}
		links = append(links, fmt.Sprintf("l/%s", link))
	}
	cacheID, err := getCacheID(getChainID(imageManifest.RootFS.Layers))
	if err != nil {
		return gerrors.Wrap(err)
	}
	if err := os.WriteFile(filepath.Join(DockerRoot, DockerOverlay2, cacheID, "lower"), []byte(strings.Join(links, ":")), 0644); err != nil {
		return gerrors.Wrap(err)
	}

	return nil
}

func getChainID(layers []string) string {
	id := layers[0]
	for _, layer := range layers[1:] {
		id = digest.FromString(id + " " + layer).String()
	}
	return id
}

func tarWriteFile(writer *tar.Writer, path string, relTo string) error {
	info, err := os.Lstat(path)
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
	name, err := filepath.Rel(relTo, path)
	if err != nil {
		return gerrors.Wrap(err)
	}
	var header *tar.Header
	if info.Mode()&os.ModeSymlink != 0 {
		link, err := os.Readlink(path)
		if err != nil {
			return gerrors.Wrap(err)
		}
		header, err = tar.FileInfoHeader(info, link)
	} else {
		header, err = tar.FileInfoHeader(info, "")
	}
	if err != nil {
		return gerrors.Wrap(err)
	}
	header.Name = filepath.ToSlash(name)
	if err := writer.WriteHeader(header); err != nil {
		return gerrors.Wrap(err)
	}

	if header.Typeflag == tar.TypeReg {
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

func (i *ImageTag) Repo() string {
	return strings.Split(i.Name, ":")[0]
}

func extractImageTag(diffPath string) (*ImageTag, error) {
	diffFile, err := os.Open(diffPath)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	defer func() { _ = diffFile.Close() }()
	diffReader := tar.NewReader(diffFile)
	for {
		header, err := diffReader.Next()
		if err == io.EOF {
			break
		} else if err != nil {
			return nil, gerrors.Wrap(err)
		}
		if header.Name == "tag.json" {
			imageTagBytes, err := io.ReadAll(diffReader)
			if err != nil {
				return nil, gerrors.Wrap(err)
			}
			var imageTag ImageTag
			if err := json.Unmarshal(imageTagBytes, &imageTag); err != nil {
				return nil, gerrors.Wrap(err)
			}
			return &imageTag, nil
		}
	}
	return nil, gerrors.New("no tag.json")
}

func getCacheID(chainID string) (string, error) {
	chainDigest, err := digest.Parse(chainID)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	cacheIDBytes, err := os.ReadFile(filepath.Join(DockerRoot, DockerLayerdb, chainDigest.Encoded(), "cache-id"))
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	return string(cacheIDBytes), nil
}

func getImageManifest(imageID string) (*ImageManifest, error) {
	imageDigest, err := digest.Parse(imageID)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	imageManifestBytes, err := os.ReadFile(filepath.Join(DockerRoot, DockerImagedbContent, imageDigest.Encoded()))
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	var imageManifest ImageManifest
	if err := json.Unmarshal(imageManifestBytes, &imageManifest); err != nil {
		return nil, gerrors.Wrap(err)
	}
	return &imageManifest, nil
}

func getCacheLink(cacheID string) (string, error) {
	link, err := os.ReadFile(filepath.Join(DockerRoot, DockerOverlay2, cacheID, "link"))
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	return string(link), nil
}
