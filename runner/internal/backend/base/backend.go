package base

import (
	"context"
	"errors"
	"fmt"
	"github.com/dstackai/dstack/runner/internal/container"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/models"
	"github.com/dstackai/dstack/runner/internal/repo"
	"gopkg.in/yaml.v2"
	"os"
	"strings"
	"time"
)

func LoadRunnerState(ctx context.Context, storage Storage, id string, out interface{}) error {
	runnerFilepath := fmt.Sprintf("runners/%s.yaml", id)
	log.Trace(ctx, "Load runner state from the storage", "ID", id)
	content, err := GetObject(ctx, storage, runnerFilepath)
	if err != nil {
		return gerrors.Wrap(err)
	}
	err = yaml.Unmarshal(content, out)
	if err != nil {
		return gerrors.Wrap(err)
	}
	if out == nil {
		return gerrors.New("State is empty. Data not loading")
	}
	return nil
}

func RefetchJob(ctx context.Context, storage Storage, job *models.Job) error {
	log.Trace(ctx, "Refetching job from state", "ID", job.JobID)
	content, err := GetObject(ctx, storage, job.JobFilepath())
	if err != nil {
		return gerrors.Wrap(err)
	}
	return gerrors.Wrap(yaml.Unmarshal(content, job))
}

func GetJobByPath(ctx context.Context, storage Storage, path string, job *models.Job) error {
	log.Trace(ctx, "Fetching job by path", "Path", path)
	content, err := GetObject(ctx, storage, path)
	if err != nil {
		return gerrors.Wrap(err)
	}
	return gerrors.Wrap(yaml.Unmarshal(content, job))
}

func UpdateState(ctx context.Context, storage Storage, job *models.Job) error {
	log.Trace(ctx, "Marshaling job")
	content, err := yaml.Marshal(job)
	if err != nil {
		return gerrors.Wrap(err)
	}
	jobFilepath := job.JobFilepath()
	log.Trace(ctx, "Write to file job", "Path", jobFilepath)
	if err = PutObject(ctx, storage, jobFilepath, content); err != nil {
		return gerrors.Wrap(err)
	}
	// should it be a job.HubUserName?
	log.Trace(ctx, "Fetching list jobs", "Repo username", job.RepoUserName, "Repo name", job.RepoName, "Job ID", job.JobID)
	files, err := ListObjects(ctx, storage, job.JobHeadFilepathPrefix())
	if err != nil {
		return gerrors.Wrap(err)
	}
	if len(files) > 1 {
		return gerrors.Newf("unexpected blob listing result %s [%d]", strings.Join(files, ","), len(files))
	}
	jobHeadFilepath := job.JobHeadFilepath()
	if len(files) == 1 {
		file := files[0]
		log.Trace(ctx, "Renaming file job", "From", file, "To", jobHeadFilepath)
		if err = storage.Rename(ctx, file, jobHeadFilepath); err != nil {
			return gerrors.Wrap(err)
		}
	}
	return nil
}

func GetRepoArchive(ctx context.Context, storage Storage, path, dir string) error {
	archive, err := os.CreateTemp("", "archive-*.tar")
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = os.Remove(archive.Name()) }()
	if err := DownloadFile(ctx, storage, path, archive.Name()); err != nil {
		return gerrors.Wrap(err)
	}
	if err := repo.ExtractArchive(ctx, archive.Name(), dir); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

var ErrBuildNotFound = errors.New("build not found")

func GetBuildDiffInfo(ctx context.Context, storage Storage, spec *container.BuildSpec) (*StorageObject, error) {
	prefix := getBuildDiffPrefix(spec)
	builds := make([]*StorageObject, 0)
	ch, errCh := storage.List(ctx, prefix)
	for item := range ch {
		item.Key = prefix + item.Key
		builds = append(builds, item)
	}
	if err := <-errCh; err != nil {
		return nil, gerrors.Wrap(err)
	}
	if len(builds) == 1 {
		return builds[0], nil
	}
	return nil, gerrors.Wrap(ErrBuildNotFound)
}

func PutBuildDiff(ctx context.Context, storage Storage, src string, spec *container.BuildSpec) error {
	newDiffKey := getBuildDiffName(spec)
	oldDiff, err := GetBuildDiffInfo(ctx, storage, spec)
	if err == nil {
		log.Trace(ctx, "Deleting old build diff", "key", oldDiff.Key)
		if err = storage.Delete(ctx, oldDiff.Key); err != nil {
			return gerrors.Wrap(err)
		}
	} else if !errors.Is(err, ErrBuildNotFound) {
		return gerrors.Wrap(err)
	}
	log.Trace(ctx, "Uploading new build diff", "key", newDiffKey)
	return gerrors.Wrap(UploadFile(ctx, storage, src, newDiffKey))
}

func getBuildDiffPrefix(spec *container.BuildSpec) string {
	return fmt.Sprintf(
		"builds/%s;%s;%s;%s;%s;",
		models.EscapeHead(spec.ConfigurationType),
		models.EscapeHead(spec.ConfigurationPath),
		models.EscapeHead(spec.WorkDir),
		models.EscapeHead(spec.BaseImageName),
		models.EscapeHead(spec.Platform),
	)
}

func getBuildDiffName(spec *container.BuildSpec) string {
	return fmt.Sprintf(
		"%s%s;%d.tar",
		getBuildDiffPrefix(spec),
		models.EscapeHead(spec.Hash()),
		time.Now().Unix(), // created timestamp
	)
}
