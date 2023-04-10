package executor

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/docker/docker/api/types"
	"io"
	"os"
	"path"
	"path/filepath"
	"strconv"
	"time"

	"github.com/docker/docker/api/types/mount"
	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/artifacts"
	"github.com/dstackai/dstack/runner/internal/backend"
	"github.com/dstackai/dstack/runner/internal/common"
	"github.com/dstackai/dstack/runner/internal/container"
	"github.com/dstackai/dstack/runner/internal/environment"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/ports"
	"github.com/dstackai/dstack/runner/internal/repo"
	"github.com/dstackai/dstack/runner/internal/states"
	"github.com/dstackai/dstack/runner/internal/stream"
)

type Executor struct {
	backend        backend.Backend
	configDir      string
	config         *Config
	engine         *container.Engine
	cacheArtifacts []artifacts.Artifacter
	artifactsIn    []artifacts.Artifacter
	artifactsOut   []artifacts.Artifacter
	artifactsFUSE  []artifacts.Artifacter
	repo           *repo.Manager
	pm             ports.Manager
	portID         string
	streamLogs     *stream.Server
	stoppedCh      chan struct{}
}

func New(b backend.Backend) *Executor {
	return &Executor{
		backend:   b,
		engine:    container.NewEngine(),
		stoppedCh: make(chan struct{}),
	}
}

func (ex *Executor) SetStreamLogs(w *stream.Server) {
	ex.streamLogs = w
}

func (ex *Executor) Init(ctx context.Context, configDir string) error {
	defer func() {
		if r := recover(); r != nil {
			log.Error(ctx, "[PANIC]", "", r)
			time.Sleep(1 * time.Second)
			panic(r)
		}
	}()
	ex.configDir = configDir
	err := ex.loadConfig(configDir)
	if err != nil {
		return err
	}
	attemts := 0
	for attemts < consts.MAX_ATTEMPTS {
		err = ex.backend.Init(ctx, ex.config.Id)
		if err != nil && !errors.Is(err, backend.ErrNotFoundTask) {
			panic(err)
		}
		if err == nil {
			break
		}
		attemts++
		time.Sleep(consts.DELAY_TRY)
	}
	if attemts == consts.MAX_ATTEMPTS {
		return err
	}

	//ex.pm = ports.NewSingle(ex.config.ExposePorts())
	ex.pm = ports.NewSystem()
	job := ex.backend.Job(ctx)

	//Update port logs
	if ex.streamLogs != nil {
		job.Environment["WS_LOGS_PORT"] = strconv.Itoa(ex.streamLogs.Port())
		if err = ex.backend.UpdateState(ctx); err != nil {
			return gerrors.Wrap(err)
		}
	}

	for _, artifact := range job.Artifacts {
		artOut := ex.backend.GetArtifact(ctx, job.RunName, artifact.Path, path.Join("artifacts", job.RepoHostNameWithPort(), job.RepoUserName, job.RepoName, job.JobID, artifact.Path), artifact.Mount)
		if artOut != nil {
			ex.artifactsOut = append(ex.artifactsOut, artOut)
		}
		if artifact.Mount {
			art := ex.backend.GetArtifact(ctx, job.RunName, artifact.Path, path.Join("artifacts", job.RepoHostNameWithPort(), job.RepoUserName, job.RepoName, job.JobID, artifact.Path), artifact.Mount)
			if art != nil {
				ex.artifactsFUSE = append(ex.artifactsFUSE, art)
			}
		}
	}

	cloudLog := ex.backend.CreateLogger(ctx, fmt.Sprintf("/dstack/runners/%s", ex.backend.Bucket(ctx)), job.RunnerID)
	log.SetCloudLogger(cloudLog)
	return nil
}

func (ex *Executor) Run(ctx context.Context) error {
	runCtx := context.Background()
	defer func() {
		if r := recover(); r != nil {
			log.Error(runCtx, "[PANIC]", "", r)
			job := ex.backend.Job(runCtx)
			job.Status = states.Failed
			_ = ex.backend.UpdateState(runCtx)
			time.Sleep(1 * time.Second)
			panic(r)
		}
	}()
	erCh := make(chan error)
	go ex.runJob(runCtx, erCh, ex.stoppedCh)
	timer := time.NewTicker(consts.DELAY_READ_STATUS)
	for {
		select {
		case <-timer.C:
			stopped, err := ex.backend.CheckStop(runCtx)
			if err != nil {
				return err
			}
			if stopped {
				log.Info(runCtx, "Stopped")
				ex.Stop()
				log.Info(runCtx, "Waiting job end")
				err = <-erCh
				job := ex.backend.Job(runCtx)
				job.Status = states.Stopped
				_ = ex.backend.UpdateState(runCtx)
				return err
			}
		case <-ctx.Done():
			log.Info(runCtx, "Stopped")
			ex.Stop()
			log.Info(runCtx, "Waiting job end")
			err := <-erCh
			job := ex.backend.Job(runCtx)
			job.Status = states.Stopped
			_ = ex.backend.UpdateState(runCtx)
			if err != nil {
				return gerrors.Wrap(err)
			}
			return nil
		case errRun := <-erCh:
			job := ex.backend.Job(runCtx)
			if errRun == nil {
				job.Status = states.Done
			} else {
				// The container may fail due to instance interruption.
				// In this case we'll let the CLI/hub update the job state accodingly.
				isInterrupted, err := ex.backend.IsInterrupted(runCtx)
				if err != nil {
					log.Error(runCtx, "Failed to check if spot was interrupted", "err", err)
				} else if isInterrupted {
					log.Trace(runCtx, "Spot was interrupted")
					return nil
				}
				log.Error(runCtx, "Failed run", "err", errRun)
				job.Status = states.Failed
			}
			_ = ex.backend.UpdateState(runCtx)
			return errRun
		}
	}
}

func (ex *Executor) Stop() {
	select {
	case <-ex.stoppedCh:
		return
	default:
	}
	close(ex.stoppedCh)
}

func (ex *Executor) runJob(ctx context.Context, erCh chan error, stoppedCh chan struct{}) {
	defer func() {
		if r := recover(); r != nil {
			log.Error(ctx, "[PANIC]", "", r)
			job := ex.backend.Job(ctx)
			job.Status = states.Failed
			_ = ex.backend.UpdateState(ctx)
			time.Sleep(1 * time.Second)
			panic(r)
		}
	}()
	job := ex.backend.Job(ctx)
	jctx := log.AppendArgsCtx(ctx,
		"run_name", job.RunName,
		"job_id", job.JobID,
		"workflow", job.WorkflowName,
	)
	var err error
	log.Trace(jctx, "Register in port manager")
	ex.portID, err = ex.pm.Register(job.PortCount, job.Ports)
	if err != nil {
		erCh <- gerrors.Wrap(err)
		return
	}
	defer ex.pm.Unregister(ex.portID)
	log.Trace(jctx, "Ports gotten", "ports", ex.pm.Ports(ex.portID))
	{
		job.Ports = ex.pm.Ports(ex.portID)
		if ex.config.Hostname != nil {
			job.HostName = *ex.config.Hostname
		}
	}
	log.Trace(jctx, "Fetching git repository")

	if err = ex.prepareGit(jctx); err != nil {
		erCh <- gerrors.Wrap(err)
		return
	}
	log.Trace(jctx, "Dependency processing")

	if err = ex.processCache(jctx); err != nil {
		erCh <- gerrors.Wrap(err)
		return
	}
	if err = ex.processDeps(jctx); err != nil {
		erCh <- gerrors.Wrap(err)
		return
	}
	{
		for _, artifact := range ex.artifactsFUSE {
			err = artifact.BeforeRun(jctx)
			if err != nil {
				erCh <- gerrors.Wrap(err)
				return
			}
		}
		if len(ex.artifactsIn) > 0 || len(ex.cacheArtifacts) > 0 {
			log.Trace(jctx, "Start downloading artifacts")
			job.Status = states.Downloading
			err = ex.backend.UpdateState(jctx)
			if err != nil {
				erCh <- gerrors.Wrap(err)
				return
			}
			for _, artifact := range ex.artifactsIn {
				err = artifact.BeforeRun(jctx)
				if err != nil {
					erCh <- gerrors.Wrap(err)
					return
				}
			}
			for _, artifact := range ex.cacheArtifacts {
				err = artifact.BeforeRun(jctx)
			}
		}
		log.Trace(jctx, "Running job")
		job.Status = states.Running

		if err = ex.backend.UpdateState(jctx); err != nil {
			erCh <- gerrors.Wrap(err)
			return
		}

		if err = ex.processJob(ctx, stoppedCh); err != nil {
			erCh <- gerrors.Wrap(err)
			return
		}
		if len(ex.artifactsOut) > 0 || len(ex.cacheArtifacts) > 0 {
			log.Trace(jctx, "Start uploading artifacts")
			job.Status = states.Uploading
			err = ex.backend.UpdateState(jctx)
			if err != nil {
				erCh <- gerrors.Wrap(err)
				return
			}
			for _, artifact := range ex.artifactsOut {
				err = artifact.AfterRun(jctx)
				if err != nil {
					erCh <- gerrors.Wrap(err)
					return
				}
			}
			for _, artifact := range ex.cacheArtifacts {
				err = artifact.AfterRun(jctx)
				if err != nil {
					erCh <- gerrors.Wrap(err)
					return
				}
			}
		}
		for _, artifact := range ex.artifactsFUSE {
			err = artifact.AfterRun(jctx)
			if err != nil {
				erCh <- gerrors.Wrap(err)
				return
			}
		}
	}
	erCh <- nil
}

func (ex *Executor) prepareGit(ctx context.Context) error {
	job := ex.backend.Job(ctx)
	dir := path.Join(common.HomeDir(), consts.RUNS_PATH, job.RunName, job.JobID)
	if _, err := os.Stat(dir); err != nil {
		if err = os.MkdirAll(dir, 0777); err != nil {
			return gerrors.Wrap(err)
		}

	}
	ex.repo = repo.NewManager(ctx, fmt.Sprintf(consts.REPO_HTTPS_URL, job.RepoHostNameWithPort(), job.RepoUserName, job.RepoName), job.RepoBranch, job.RepoHash).WithLocalPath(dir)
	cred := ex.backend.GitCredentials(ctx)
	if cred != nil {
		log.Trace(ctx, "Credentials is not empty")
		switch cred.Protocol {
		case "https":
			log.Trace(ctx, "Select HTTPS protocol")
			if cred.OAuthToken == nil {
				log.Error(ctx, "OAuth token is empty")
				break
			}
			ex.repo.WithTokenAuth(*cred.OAuthToken)
		case "ssh":
			log.Trace(ctx, "Select SSH protocol")
			if cred.PrivateKey == nil {
				log.Error(ctx, "Private key is empty")
				break
			}
			password := ""
			if cred.Passphrase != nil {
				password = *cred.Passphrase
			}
			ex.repo = repo.NewManager(ctx, fmt.Sprintf(consts.REPO_GIT_URL, job.RepoHostNameWithPort(), job.RepoUserName, job.RepoName), job.RepoBranch, job.RepoHash).WithLocalPath(dir)
			ex.repo.WithSSHAuth(*cred.PrivateKey, password)
		default:
			log.Error(ctx, "Unsupported protocol", "protocol", cred.Protocol)
		}
	}

	if err := ex.repo.Checkout(); err != nil {
		log.Trace(ctx, "GIT checkout error", "err", err, "GIT URL", ex.repo.URL())
		return gerrors.Wrap(err)
	}
	if job.RepoDiff != "" {
		if err := repo.ApplyDiff(ctx, dir, job.RepoDiff); err != nil {
			return gerrors.Wrap(err)
		}
	}
	return nil
}

func (ex *Executor) processDeps(ctx context.Context) error {
	job := ex.backend.Job(ctx)
	for _, dep := range job.Deps {
		listDir, err := ex.backend.ListSubDir(ctx, fmt.Sprintf("jobs/%s/%s/%s/%s,", dep.RepoHostNameWithPort(), dep.RepoUserName, dep.RepoName, dep.RunName))
		if err != nil {
			return gerrors.Wrap(err)
		}
		for _, pathJob := range listDir {
			jobDep, err := ex.backend.GetJobByPath(ctx, pathJob)
			if err != nil {
				return gerrors.Wrap(err)
			}
			for _, artifact := range jobDep.Artifacts {
				artIn := ex.backend.GetArtifact(ctx, jobDep.RunName, artifact.Path, path.Join("artifacts", jobDep.RepoHostNameWithPort(), jobDep.RepoUserName, jobDep.RepoName, jobDep.JobID, artifact.Path), artifact.Mount)
				if artIn != nil {
					ex.artifactsIn = append(ex.artifactsIn, artIn)
				}
			}
		}
	}
	return nil
}

func (ex *Executor) processCache(ctx context.Context) error {
	job := ex.backend.Job(ctx)
	username := job.LocalRepoUserEmail
	if len(username) == 0 {
		username = "default"
	}
	for _, cache := range job.Cache {
		cacheArt := ex.backend.GetArtifact(ctx, job.RunName, cache.Path, path.Join("cache", job.RepoHostNameWithPort(), job.RepoUserName, job.RepoName, username, job.WorkflowName, cache.Path), false)
		if cacheArt != nil {
			ex.cacheArtifacts = append(ex.cacheArtifacts, cacheArt)
		}
	}
	return nil
}

func (ex *Executor) environment(ctx context.Context) []string {
	log.Trace(ctx, "Start generate env")
	job := ex.backend.Job(ctx)
	env := environment.New()

	cons := make(map[string]string)
	cons["PYTHONUNBUFFERED"] = "1"
	if job.JobID != "" {
		cons["JOB_ID"] = job.JobID
	}
	if job.RunName != "" {
		cons["RUN_NAME"] = job.RunName
	}
	if ex.config.Hostname != nil {
		cons["JOB_HOSTNAME"] = *ex.config.Hostname
		cons["HOSTNAME"] = *ex.config.Hostname
	}
	pos := 0
	for _, v := range ex.pm.Ports(ex.portID) {
		cons[fmt.Sprintf("PORT_%d", pos)] = v
		cons[fmt.Sprintf("JOB_PORT_%d", pos)] = v
		pos++
	}

	if job.MasterJobID != "" {
		master := ex.backend.MasterJob(ctx)
		cons["MASTER_ID"] = master.JobID
		cons["MASTER_HOSTNAME"] = master.HostName
		cons["MASTER_JOB_ID"] = master.JobID
		cons["MASTER_JOB_HOSTNAME"] = master.HostName
		pos = 0
		if master.Ports != nil {
			for _, v := range master.Ports {
				cons[fmt.Sprintf("MASTER_JOB_PORT_%d", pos)] = v
				cons[fmt.Sprintf("MASTER_PORT_%d", pos)] = v
				pos++
			}
		}
	}

	env.AddMapString(cons)
	env.AddMapString(job.Environment)
	//env.AddMapInterface(job.Variables)
	secrets, err := ex.backend.Secrets(ctx)
	if err != nil {
		log.Error(ctx, "Fail fetching secrets", "err", err)
	}
	env.AddMapString(secrets)

	log.Trace(ctx, "Stop generate env", "slice", env.ToSlice())
	return env.ToSlice()

}

func (ex *Executor) processJob(ctx context.Context, stoppedCh chan struct{}) error {
	job := ex.backend.Job(ctx)
	resource := ex.backend.Requirements(ctx)
	bindings := make([]mount.Mount, 0)
	bindings = append(bindings, mount.Mount{
		Type:   mount.TypeBind,
		Source: path.Join(common.HomeDir(), consts.RUNS_PATH, job.RunName, job.JobID),
		Target: "/workflow",
	})
	for _, artifact := range ex.artifactsIn {
		art, err := artifact.DockerBindings(path.Join("/workflow", job.WorkingDir))
		if err != nil {
			return gerrors.Wrap(err)
		}
		bindings = append(bindings, art...)
	}
	for _, artifact := range ex.artifactsOut {
		art, err := artifact.DockerBindings(path.Join("/workflow", job.WorkingDir))
		if err != nil {
			return gerrors.Wrap(err)
		}
		bindings = append(bindings, art...)
	}
	for _, artifact := range ex.cacheArtifacts {
		art, err := artifact.DockerBindings(path.Join("/workflow", job.WorkingDir))
		if err != nil {
			return gerrors.Wrap(err)
		}
		bindings = append(bindings, art...)
	}
	logger := ex.backend.CreateLogger(ctx, fmt.Sprintf("/dstack/jobs/%s/%s/%s/%s", ex.backend.Bucket(ctx), job.RepoHostNameWithPort(), job.RepoUserName, job.RepoName), job.RunName)
	secrets, err := ex.backend.Secrets(ctx)
	if err != nil {
		log.Error(ctx, "Fail fetching secrets", "err", err)
	}
	var interpolator VariablesInterpolator
	interpolator.Add("secrets", secrets)
	username, err := interpolator.Interpolate(ctx, job.RegistryAuth.Username)
	if err != nil {
		log.Error(ctx, "Failed interpolating registry_auth.username", "err", err, "username", job.RegistryAuth.Username)
	}
	password, err := interpolator.Interpolate(ctx, job.RegistryAuth.Password)
	if err != nil {
		log.Error(ctx, "Failed interpolating registry_auth.password", "err", err, "password", job.RegistryAuth.Password)
	}
	spec := &container.Spec{
		Image:              job.Image,
		RegistryAuthBase64: makeRegistryAuthBase64(username, password),
		WorkDir:            path.Join("/workflow", job.WorkingDir),
		Commands:           container.ShellCommands(job.Commands),
		Entrypoint:         job.Entrypoint,
		Env:                ex.environment(ctx),
		Mounts:             uniqueMount(bindings),
		ExposedPorts:       ex.pm.ExposedPorts(ex.portID),
		BindingPorts:       ex.pm.BindPorts(ex.portID),
		ShmSize:            resource.ShmSize,
	}
	logGroup := fmt.Sprintf("/jobs/%s/%s/%s", job.RepoHostNameWithPort(), job.RepoUserName, job.RepoName)
	fileLog, err := createLocalLog(filepath.Join(ex.configDir, "logs", logGroup), job.RunName)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer fileLog.Close()

	ml := io.MultiWriter(logger, ex.streamLogs, fileLog)
	docker, err := ex.engine.Create(ctx, spec, ml)
	if err != nil {
		return gerrors.Wrap(err)
	}
	err = docker.Run(ctx)
	if err != nil {
		return gerrors.Wrap(err)
	}
	errCh := make(chan error)
	go func() {
		defer func() {
			ex.streamLogs.Close()
			log.Info(ctx, "Docker log stream closed")
		}()
		err = docker.Wait(ctx)
		if err != nil && !errors.Is(err, context.Canceled) {
			errCh <- gerrors.Wrap(err)
		}
		errCh <- nil
	}()
	select {
	case err = <-errCh:
		if err != nil {
			return gerrors.Wrap(err)
		}
		return nil
	case <-stoppedCh:
		err = docker.Stop(ctx)
		if err != nil {
			return gerrors.Wrap(err)
		}
		return nil
	}
}

func (ex *Executor) Shutdown(ctx context.Context) {
	defer func() {
		if r := recover(); r != nil {
			log.Error(ctx, "[PANIC]", "", r)
			panic(r)
		}
	}()
	err := ex.backend.Shutdown(ctx)
	if err != nil {
		log.Error(ctx, "Shutdown", "err", err)
		return
	}
}

func uniqueMount(m []mount.Mount) []mount.Mount {
	u := make(map[string]mount.Mount)
	result := make([]mount.Mount, 0, len(m))
	for _, item := range m {
		u[item.Target] = item
	}
	for _, item := range u {
		result = append(result, item)
	}
	return result
}

func createLocalLog(dir, fileName string) (*os.File, error) {
	if _, err := os.Stat(dir); err != nil {
		if err = os.MkdirAll(dir, 0777); err != nil {
			return nil, gerrors.Wrap(err)
		}
	}
	fileLog, err := os.OpenFile(filepath.Join(dir, fmt.Sprintf("%s.log", fileName)), os.O_RDWR|os.O_CREATE|os.O_APPEND, 0o777)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return fileLog, nil
}

func makeRegistryAuthBase64(username string, password string) string {
	if username == "" && password == "" {
		return ""
	}
	authConfig := types.AuthConfig{
		Username: username,
		Password: password,
	}
	encodedJSON, err := json.Marshal(authConfig)
	if err != nil {
		panic(err)
	}
	return base64.URLEncoding.EncodeToString(encodedJSON)
}
