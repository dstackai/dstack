package gcp

import (
	"context"
	"errors"
	"io"
	"os"
	"path"
	"strings"

	"github.com/docker/docker/api/types/mount"
	"gopkg.in/yaml.v2"

	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/backend"
	"github.com/dstackai/dstack/runner/internal/backend/base"
	"github.com/dstackai/dstack/runner/internal/common"
	"github.com/dstackai/dstack/runner/internal/docker"
	"github.com/dstackai/dstack/runner/internal/gerrors"
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
	logging       *GCPLogging
	runnerID      string
	state         *models.State
}

type GCPConfigFile struct {
	Project string `yaml:"project"`
	Zone    string `yaml:"zone"`
	Bucket  string `yaml:"bucket"`
}

func init() {
	backend.RegisterBackend("gcp", func(ctx context.Context, pathConfig string) (backend.Backend, error) {
		configFile := GCPConfigFile{}
		log.Trace(ctx, "Read config file", "path", pathConfig)
		fileContent, err := os.ReadFile(pathConfig)
		if err != nil {
			return nil, gerrors.Wrap(err)
		}
		log.Trace(ctx, "Unmarshal config")
		err = yaml.Unmarshal(fileContent, &configFile)
		if err != nil {
			return nil, gerrors.Wrap(err)
		}
		return New(configFile.Project, configFile.Zone, configFile.Bucket)
	})
}

func New(project, zone, bucket string) (*GCPBackend, error) {
	storage, err := NewGCPStorage(project, bucket)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	compute := NewGCPCompute(project, zone)
	if compute == nil {
		return nil, gerrors.Wrap(err)
	}
	secretManager := NewGCPSecretManager(project, bucket)
	if secretManager == nil {
		return nil, gerrors.Wrap(err)
	}
	logging := NewGCPLogging(project)
	return &GCPBackend{
		project:       project,
		zone:          zone,
		bucket:        bucket,
		storage:       storage,
		compute:       compute,
		secretManager: secretManager,
		logging:       logging,
	}, nil
}

func (gbackend *GCPBackend) Init(ctx context.Context, ID string) error {
	gbackend.runnerID = ID
	if err := base.LoadRunnerState(ctx, gbackend.storage, ID, &gbackend.state); err != nil {
		return gerrors.Wrap(err)
	}
	ip, err := gbackend.compute.GetInstancePublicIP(ctx, gbackend.state.RequestID)
	if err != nil {
		return gerrors.Wrap(err)
	}
	log.Trace(ctx, "Setting GCP instance IP", "ip", ip)
	gbackend.state.Job.HostName = ip
	return nil
}

func (gbackend *GCPBackend) Job(ctx context.Context) *models.Job {
	log.Trace(ctx, "Getting job from state")
	log.Trace(ctx, "Get job", "ID", gbackend.state.Job.JobID)
	return gbackend.state.Job
}

func (gbackend *GCPBackend) RefetchJob(ctx context.Context) (*models.Job, error) {
	if err := base.RefetchJob(ctx, gbackend.storage, gbackend.state.Job); err != nil {
		return nil, gerrors.Wrap(err)
	}
	return gbackend.state.Job, nil
}

func (gbackend *GCPBackend) UpdateState(ctx context.Context) error {
	return gerrors.Wrap(base.UpdateState(ctx, gbackend.storage, gbackend.state.Job))
}

func (gbackend *GCPBackend) IsInterrupted(ctx context.Context) (bool, error) {
	if !gbackend.state.Resources.Spot {
		return false, nil
	}
	return gbackend.compute.IsInterruptedSpot(ctx, gbackend.state.RequestID)
}

func (gbackend *GCPBackend) Stop(ctx context.Context) error {
	err := gbackend.compute.StopInstance(ctx, gbackend.state.RequestID)
	if err != nil {
		return gerrors.Wrap(err)
	}
	return gerrors.Wrap(gbackend.cleanup(ctx))
}

func (gbackend *GCPBackend) Shutdown(ctx context.Context) error {
	err := gbackend.compute.TerminateInstance(ctx, gbackend.state.RequestID)
	if err != nil {
		return gerrors.Wrap(err)
	}
	return gerrors.Wrap(gbackend.cleanup(ctx))
}

func (gbackend *GCPBackend) GetArtifact(ctx context.Context, runName, localPath, remotePath string, mount bool) base.Artifacter {
	workDir := path.Join(gbackend.GetTMPDir(ctx), consts.USER_ARTIFACTS_DIR, runName)
	return NewGCPArtifacter(gbackend.storage, workDir, localPath, remotePath, false)
}

func (gbackend *GCPBackend) GetCache(ctx context.Context, runName, localPath, remotePath string) base.Artifacter {
	workDir := path.Join(gbackend.GetTMPDir(ctx), consts.USER_ARTIFACTS_DIR, runName)
	return NewGCPArtifacter(gbackend.storage, workDir, localPath, remotePath, true)
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
	logger := gbackend.logging.NewGCPLogger(ctx, gbackend.state.Job.JobID, logGroup, logName)
	if logger == nil {
		log.Error(ctx, "Failed to create logger")
		return nil
	}
	logger.Launch(ctx)
	return logger
}

func (gbackend *GCPBackend) ListSubDir(ctx context.Context, dir string) ([]string, error) {
	return base.ListObjects(ctx, gbackend.storage, dir)
}

func (gbackend *GCPBackend) GetJobByPath(ctx context.Context, path string) (*models.Job, error) {
	job := new(models.Job)
	if err := base.GetJobByPath(ctx, gbackend.storage, path, job); err != nil {
		return nil, gerrors.Wrap(err)
	}
	return job, nil
}

func (gbackend *GCPBackend) Bucket(ctx context.Context) string {
	log.Trace(ctx, "Getting bucket")
	return gbackend.bucket
}

func (gbackend *GCPBackend) Secrets(ctx context.Context) (map[string]string, error) {
	log.Trace(ctx, "Getting secrets")
	prefix := gbackend.state.Job.SecretsPrefix()
	secretFilenames, err := base.ListObjects(ctx, gbackend.storage, prefix)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	secrets := make(map[string]string, 0)
	for _, secretFilename := range secretFilenames {
		secretName := strings.ReplaceAll(secretFilename, prefix, "")
		secretValue, err := gbackend.secretManager.FetchSecret(ctx, gbackend.state.Job.RepoId, secretName)
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

func (gbackend *GCPBackend) GitCredentials(ctx context.Context) *models.GitCredentials {
	log.Trace(ctx, "Getting credentials")
	creds, err := gbackend.secretManager.FetchCredentials(ctx, gbackend.state.Job.RepoId)
	if err != nil {
		return nil
	}
	return creds
}

func (gbackend *GCPBackend) GetRepoDiff(ctx context.Context, path string) (string, error) {
	diff, err := base.GetObject(ctx, gbackend.storage, path)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	return string(diff), nil
}

func (gbackend *GCPBackend) GetRepoArchive(ctx context.Context, path, dir string) error {
	return gerrors.Wrap(base.GetRepoArchive(ctx, gbackend.storage, path, dir))
}

func (gbackend *GCPBackend) GetBuildDiffInfo(ctx context.Context, spec *docker.BuildSpec) (*base.StorageObject, error) {
	obj, err := base.GetBuildDiffInfo(ctx, gbackend.storage, spec)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return obj, nil
}

func (gbackend *GCPBackend) GetBuildDiff(ctx context.Context, key, dst string) error {
	return gerrors.Wrap(base.DownloadFile(ctx, gbackend.storage, key, dst))
}

func (gbackend *GCPBackend) PutBuildDiff(ctx context.Context, src string, spec *docker.BuildSpec) error {
	return gerrors.Wrap(base.PutBuildDiff(ctx, gbackend.storage, src, spec))
}

func (gbackend *GCPBackend) GetTMPDir(ctx context.Context) string {
	return path.Join(common.HomeDir(), consts.TMP_DIR_PATH)
}

func (gbackend *GCPBackend) GetDockerBindings(ctx context.Context) []mount.Mount {
	return []mount.Mount{}
}

func (gbackend *GCPBackend) cleanup(ctx context.Context) error {
	err := gbackend.compute.instancesClient.Close()
	if err != nil {
		return gerrors.Wrap(err)
	}
	err = gbackend.storage.client.Close()
	if err != nil {
		return gerrors.Wrap(err)
	}
	err = gbackend.secretManager.client.Close()
	if err != nil {
		return gerrors.Wrap(err)
	}
	return gerrors.Wrap(gbackend.logging.client.Close())
}
