package gcp

import (

	// "errors"
	// "fmt"

	// "os"
	// "path"
	// "strings"
	// "time"

	// "github.com/dstackai/dstack/runner/consts"
	"context"
	"errors"
	"fmt"
	"io"
	"strings"

	"github.com/dstackai/dstack/runner/internal/artifacts"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"gopkg.in/yaml.v2"

	// "github.com/dstackai/dstack/runner/internal/artifacts/simple"

	// "github.com/dstackai/dstack/runner/internal/common"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/models"
)

type GCPBackend struct {
	project       string
	zone          string
	bucket        string
	storage       *GCPStorage
	compute       *GCPCompute
	secretManager *GCPSecretManager
	runnerID      string
	state         *models.State
	artifacts     []artifacts.Artifacter
}

// func init() {
// 	backend.RegisterBackend("aws", func(ctx context.Context, pathConfig string) (backend.Backend, error) {
// 		// TODO read config
// 		// log.Trace(ctx, "Read config file", "path", pathConfig)
// 		// theConfig, err := ioutil.ReadFile(pathConfig)
// 		// if err != nil {
// 		// 	return nil, gerrors.Wrap(err)
// 		// }
// 		// log.Trace(ctx, "Unmarshal config")
// 		// err = yaml.Unmarshal(theConfig, &file)
// 		// if err != nil {
// 		// 	return nil, gerrors.Wrap(err)
// 		// }
// 		return New("dstack", "us-central1-a", "dstack-bucket"), nil
// 	})
// }

func New(project, zone, bucket string) *GCPBackend {
	storage, err := NewGCPStorage(project, bucket)
	if err != nil {
		return nil
	}
	compute := NewGCPCompute(project, zone)
	if compute == nil {
		return nil
	}
	secretManager := NewGCPSecretManager(project, bucket)
	if secretManager == nil {
		return nil
	}
	return &GCPBackend{
		project:       project,
		zone:          zone,
		bucket:        bucket,
		storage:       storage,
		compute:       compute,
		secretManager: secretManager,
	}
}

func (gbackend *GCPBackend) Init(ctx context.Context, ID string) error {
	gbackend.runnerID = ID
	runnerFilepath := fmt.Sprintf("runners/%s.yaml", ID)
	contents, err := gbackend.storage.GetFile(ctx, runnerFilepath)
	if err != nil {
		return gerrors.Wrap(err)
	}
	err = yaml.Unmarshal(contents, &gbackend.state)
	if err != nil {
		return gerrors.Wrap(err)
	}
	if gbackend.state == nil {
		return gerrors.New("State is empty. Data not loading")
	}
	return nil
}

func (gbackend *GCPBackend) Job(ctx context.Context) *models.Job {
	log.Trace(ctx, "Getting job from state")
	log.Trace(ctx, "Get job", "job ID", gbackend.state.Job.JobID)
	return gbackend.state.Job
}

func (gbackend *GCPBackend) UpdateState(ctx context.Context) error {
	log.Trace(ctx, "Fetching list jobs", "Repo username", gbackend.state.Job.RepoUserName, "Repo name", gbackend.state.Job.RepoName, "Job ID", gbackend.state.Job.JobID)
	files, err := gbackend.storage.ListFile(ctx, gbackend.state.Job.JobHeadFilepathPrefix())
	if err != nil {
		return gerrors.Wrap(err)
	}
	for _, file := range files {
		log.Trace(ctx, "Deleting file job", "Bucket", gbackend.bucket, "Path", file)
		err = gbackend.storage.DeleteFile(ctx, file)
		if err != nil {
			return gerrors.Wrap(err)
		}
	}
	log.Trace(ctx, "Marshaling job")
	contents, err := yaml.Marshal(&gbackend.state.Job)
	if err != nil {
		return gerrors.Wrap(err)
	}
	jobFilepath := gbackend.state.Job.JobFilepath()
	log.Trace(ctx, "Write to file job", "Path", jobFilepath)
	err = gbackend.storage.PutFile(ctx, jobFilepath, contents)
	if err != nil {
		return gerrors.Wrap(err)
	}
	jobHeadFilepath := gbackend.state.Job.JobHeadFilepath()
	log.Trace(ctx, "Write to file lock job", "Path", jobHeadFilepath)
	err = gbackend.storage.PutFile(ctx, jobHeadFilepath, []byte{})
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (gbackend *GCPBackend) CheckStop(ctx context.Context) (bool, error) {
	runnerFilepath := fmt.Sprintf("runners/%s.yaml", gbackend.runnerID)
	log.Trace(ctx, "Reading metadata from state file", "path", runnerFilepath)
	status, err := gbackend.storage.GetMetadata(ctx, runnerFilepath, "status")
	if err != nil && !errors.Is(err, ErrTagNotFound) {
		return false, gerrors.Wrap(err)
	}
	if status == "stopping" {
		log.Trace(ctx, "Status equals stopping")
		return true, nil
	}
	return false, nil
}

func (gbackend *GCPBackend) Shutdown(ctx context.Context) error {
	return gbackend.compute.TerminateInstance(ctx, gbackend.state.RequestID)
}

func (gbackend *GCPBackend) Requirements(ctx context.Context) models.Requirements {
	log.Trace(ctx, "Getting requirements")
	return gbackend.state.Job.Requirements
}

func (gbackend *GCPBackend) MasterJob(ctx context.Context) *models.Job {
	// TODO
	return nil
}

func (gbackend *GCPBackend) CreateLogger(ctx context.Context, logGroup, logName string) io.Writer {
	logger := NewGCPLogger(ctx, gbackend.project, gbackend.state.Job.JobID, logGroup, logName)
	if logger == nil {
		log.Error(ctx, "Failed to create logger")
		return nil
	}
	logger.Launch(ctx)
	return logger
}

func (gbackend *GCPBackend) ListSubDir(ctx context.Context, dir string) ([]string, error) {
	// TODO
	return nil, nil
}

func (gbackend *GCPBackend) GetJobByPath(ctx context.Context, path string) (*models.Job, error) {
	// TODO
	return nil, nil
}

func (gbackend *GCPBackend) Bucket(ctx context.Context) string {
	log.Trace(ctx, "Getting bucket")
	return gbackend.bucket
}

func (gbackend *GCPBackend) Secrets(ctx context.Context) (map[string]string, error) {
	log.Trace(ctx, "Getting secrets")
	prefix := gbackend.state.Job.JobRepoData().SecretsPrefix()
	secretFilenames, err := gbackend.storage.ListFile(ctx, prefix)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	secrets := make(map[string]string, 0)
	for _, secretFilename := range secretFilenames {
		secretName := strings.ReplaceAll(secretFilename, prefix, "")
		secretValue, err := gbackend.secretManager.FetchSecret(ctx, gbackend.state.Job.JobRepoData(), secretName)
		if err != nil {
			if errors.Is(err, ErrSecretNotFound) {
				continue
			}
			return nil, gerrors.Wrap(err)
		}
		secrets[secretName] = secretValue
	}
	return secrets, nil
}
