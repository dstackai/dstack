package container

import (
	"archive/tar"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/api/types/mount"
	docker "github.com/docker/docker/client"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"golang.org/x/sync/errgroup"
	"io"
	"os"
	"strings"
)

type PrebuildSpec struct {
	Image      string
	WorkDir    string
	Commands   []string
	Entrypoint []string
	Env        []string

	RepoPath string
}

type ImageManifest struct {
	Layers []string `json:"Layers"`
}

type ImageConfig struct {
	RootFS struct {
		Layers []string `json:"diff_ids"`
	} `json:"rootfs"`
}

func SaveLayer(ctx context.Context, client docker.APIClient, baseImageName, imageName, diffPath string) error {
	tempFile, err := os.CreateTemp("", "layer")
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = os.Remove(tempFile.Name()) }()

	baseInfo, _, err := client.ImageInspectWithRaw(ctx, baseImageName)
	if err != nil {
		return gerrors.Wrap(err)
	}
	imageFile, err := client.ImageSave(ctx, []string{imageName})
	if err != nil {
		return gerrors.Wrap(err)
	}
	imageReader := tar.NewReader(imageFile)

	diffFile, err := os.Create(diffPath)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = diffFile.Close() }()
	diffWriter := tar.NewWriter(diffFile)
	defer func() { _ = diffWriter.Close() }()

	log.Trace(ctx, "Producing image diff", "base", baseImageName, "image", imageName)
	for {
		header, err := imageReader.Next()
		if err != nil {
			if err == io.EOF {
				break
			}
			return gerrors.Wrap(err)
		}
		if !strings.HasSuffix(header.Name, "/layer.tar") {
			err = diffWriter.WriteHeader(header)
			if err != nil {
				return gerrors.Wrap(err)
			}
			_, err = io.Copy(diffWriter, imageReader)
			if err != nil {
				return gerrors.Wrap(err)
			}
		} else {
			// compute sha256 before saving layer
			err = tempFile.Truncate(0)
			if err != nil {
				return gerrors.Wrap(err)
			}
			_, err = tempFile.Seek(0, 0)
			if err != nil {
				return gerrors.Wrap(err)
			}
			hash := sha256.New()
			tee := io.TeeReader(imageReader, hash)
			_, err = io.Copy(tempFile, tee)
			if err != nil {
				return gerrors.Wrap(err)
			}
			layerHash := fmt.Sprintf("sha256:%x", hash.Sum(nil))
			if indexOf(baseInfo.RootFS.Layers, layerHash) != -1 {
				continue
			}
			log.Trace(ctx, "Saving image layer", "image", imageName, "hash", layerHash)
			err = diffWriter.WriteHeader(header)
			if err != nil {
				return gerrors.Wrap(err)
			}
			_, err = tempFile.Seek(0, 0)
			if err != nil {
				return gerrors.Wrap(err)
			}
			_, err = io.Copy(diffWriter, tempFile)
			if err != nil {
				return gerrors.Wrap(err)
			}
		}
	}
	return nil
}

func LoadLayer(ctx context.Context, client docker.APIClient, baseImageName, diffPath string) error {
	// use pipe to avoid writing tar to a disk
	pipeRead, pipeWriter := io.Pipe()
	errs, ctx := errgroup.WithContext(ctx)

	// process diff & base image in another thread
	errs.Go(func() error {
		imageWriter := tar.NewWriter(pipeWriter)
		defer func() {
			_ = imageWriter.Close()
			_ = pipeWriter.Close()
		}()

		diffFile, err := os.Open(diffPath)
		if err != nil {
			return gerrors.Wrap(err)
		}
		diffReader := tar.NewReader(diffFile)
		var config *ImageConfig
		var manifest []ImageManifest
		for { // write image diff
			header, err := diffReader.Next()
			if err != nil {
				if err == io.EOF {
					break
				}
				return gerrors.Wrap(err)
			}
			err = imageWriter.WriteHeader(header)
			if err != nil {
				return gerrors.Wrap(err)
			}

			if header.Name == "manifest.json" { // load and copy
				tee := io.TeeReader(diffReader, imageWriter)
				raw, err := io.ReadAll(tee)
				if err != nil {
					return gerrors.Wrap(err)
				}
				err = json.Unmarshal(raw, &manifest)
				if err != nil {
					return gerrors.Wrap(err)
				}
			} else if isConfigFile(header.Name) { // load and copy
				tee := io.TeeReader(diffReader, imageWriter)
				raw, err := io.ReadAll(tee)
				if err != nil {
					return gerrors.Wrap(err)
				}
				config = &ImageConfig{}
				err = json.Unmarshal(raw, config)
				if err != nil {
					return gerrors.Wrap(err)
				}
			} else { // just copy
				_, err = io.Copy(imageWriter, diffReader)
				if err != nil {
					return gerrors.Wrap(err)
				}
			}

		}
		if config == nil || len(manifest) != 1 {
			return gerrors.Wrap(fmt.Errorf("config or manifest is not presented in diff"))
		}

		tempFile, err := os.CreateTemp("", "layer")
		if err != nil {
			return gerrors.Wrap(err)
		}
		defer func() { _ = os.Remove(tempFile.Name()) }()
		baseFile, err := client.ImageSave(ctx, []string{baseImageName})
		if err != nil {
			return gerrors.Wrap(err)
		}
		baseReader := tar.NewReader(baseFile)
		for { // write absent layers
			header, err := baseReader.Next()
			if err != nil {
				if err == io.EOF {
					break
				}
				return gerrors.Wrap(err)
			}
			if !strings.HasSuffix(header.Name, "/layer.tar") {
				continue
			}

			// compute sha256 before adding layer
			err = tempFile.Truncate(0)
			if err != nil {
				return gerrors.Wrap(err)
			}
			_, err = tempFile.Seek(0, 0)
			if err != nil {
				return gerrors.Wrap(err)
			}
			hash := sha256.New()
			tee := io.TeeReader(baseReader, hash)
			_, err = io.Copy(tempFile, tee)
			if err != nil {
				return gerrors.Wrap(err)
			}
			layerHash := fmt.Sprintf("sha256:%x", hash.Sum(nil))
			layerIdx := indexOf(config.RootFS.Layers, layerHash)
			if layerIdx != -1 {
				return gerrors.Wrap(err)
			}
			log.Trace(ctx, "Adding image layer", "base", baseImageName, "hash", layerHash)
			// Docker may change path of the layer after running and committing
			// Use path from prebuild manifest.json
			header.Name = manifest[0].Layers[layerIdx]
			err = imageWriter.WriteHeader(header)
			if err != nil {
				return gerrors.Wrap(err)
			}
			_, err = tempFile.Seek(0, 0)
			if err != nil {
				return gerrors.Wrap(err)
			}
			_, err = io.Copy(imageWriter, tempFile)
			if err != nil {
				return gerrors.Wrap(err)
			}
		}
		return nil
	})

	// load image from the pipe
	_, err := client.ImageLoad(ctx, pipeRead, true)
	if pipeErr := errs.Wait(); pipeErr != nil {
		return gerrors.Wrap(pipeErr)
	}
	if err != nil {
		return gerrors.Wrap(err)
	}

	return nil
}

func PrebuildImage(ctx context.Context, client docker.APIClient, spec *PrebuildSpec, image string) error {
	stopTimeout := 10 * 60
	config := &container.Config{
		Image:       spec.Image,
		WorkingDir:  spec.WorkDir,
		Cmd:         spec.Commands,
		Entrypoint:  spec.Entrypoint,
		Env:         spec.Env,
		Tty:         true,
		StopTimeout: &stopTimeout,
		// todo attach stdout?
	}
	hostConfig := &container.HostConfig{
		Mounts: []mount.Mount{
			{
				Type:     mount.TypeBind,
				Source:   spec.RepoPath,
				Target:   "/workflow",
				ReadOnly: true,
			},
		},
	}
	createResp, err := client.ContainerCreate(ctx, config, hostConfig, nil, nil, "")
	if err != nil {
		return gerrors.Wrap(err)
	}
	err = client.ContainerStart(ctx, createResp.ID, types.ContainerStartOptions{})
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = client.ContainerRemove(ctx, createResp.ID, types.ContainerRemoveOptions{Force: true}) }()
	statusCh, errCh := client.ContainerWait(ctx, createResp.ID, container.WaitConditionNotRunning)
	if err != nil {
		return gerrors.Wrap(err)
	}
	// todo stream logs
	select {
	case err := <-errCh:
		if err != nil {
			return gerrors.Wrap(err)
		}
	case <-statusCh:
	}
	info, err := client.ContainerInspect(ctx, createResp.ID)
	if err != nil {
		return gerrors.Wrap(err)
	}
	if info.State.ExitCode != 0 {
		return gerrors.Wrap(ContainerExitedError{info.State.ExitCode})
	}
	_, err = client.ContainerCommit(ctx, createResp.ID, types.ContainerCommitOptions{Reference: image})
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (s *PrebuildSpec) Hash() string {
	var buffer bytes.Buffer
	buffer.WriteString(s.Image)
	buffer.WriteString("\n")
	buffer.WriteString(s.WorkDir)
	buffer.WriteString("\n")
	buffer.WriteString(strings.Join(s.Commands, " "))
	buffer.WriteString("\n")
	buffer.WriteString(strings.Join(s.Entrypoint, " "))
	buffer.WriteString("\n")
	// todo filter env
	// todo sort env keys
	buffer.WriteString(strings.Join(s.Env, ":"))
	buffer.WriteString("\n")
	return fmt.Sprintf("%x", sha256.Sum256(buffer.Bytes()))
}

func indexOf(array []string, value string) int {
	for i, item := range array {
		if item == value {
			return i
		}
	}
	return -1
}

func isConfigFile(name string) bool {
	suffix := ".json"
	return len(name) == 64+len(suffix) && !strings.Contains(name, "/") && strings.HasSuffix(name, suffix)
}
