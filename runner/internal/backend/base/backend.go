package base

import (
	"context"
	"fmt"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/models"
	"github.com/dstackai/dstack/runner/internal/repo"
	"gopkg.in/yaml.v2"
	"os"
	"strings"
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
