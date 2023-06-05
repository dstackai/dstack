package executor

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	localbackend "github.com/dstackai/dstack/runner/internal/backend/local"
	"github.com/dstackai/dstack/runner/internal/models"
	"io"
	"os"
	"path"
	"path/filepath"
	"strconv"
	"time"

	"github.com/docker/docker/api/types"

	"github.com/docker/docker/api/types/mount"
	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/consts/errorcodes"
	"github.com/dstackai/dstack/runner/consts/states"
	"github.com/dstackai/dstack/runner/internal/artifacts"
	"github.com/dstackai/dstack/runner/internal/backend"
	"github.com/dstackai/dstack/runner/internal/container"
	"github.com/dstackai/dstack/runner/internal/environment"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/ports"
	"github.com/dstackai/dstack/runner/internal/repo"
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

	job := ex.backend.Job(ctx)

	//Update port logs
	if ex.streamLogs != nil {
		job.Environment["WS_LOGS_PORT"] = strconv.Itoa(ex.streamLogs.Port())
		if err = ex.backend.UpdateState(ctx); err != nil {
			return gerrors.Wrap(err)
		}
	}

	for _, artifact := range job.Artifacts {
		artOut := ex.backend.GetArtifact(ctx, job.RunName, artifact.Path, path.Join("artifacts", job.RepoId, job.JobID, artifact.Path), artifact.Mount)
		if artOut != nil {
			ex.artifactsOut = append(ex.artifactsOut, artOut)
		}
		if artifact.Mount {
			art := ex.backend.GetArtifact(ctx, job.RunName, artifact.Path, path.Join("artifacts", job.RepoId, job.JobID, artifact.Path), artifact.Mount)
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
				containerExitedError := &container.ContainerExitedError{}
				if errors.As(errRun, containerExitedError) {
					job.ErrorCode = errorcodes.ContainerExitedWithError
					job.ContainerExitCode = fmt.Sprintf("%d", containerExitedError.ExitCode)
				}
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
	if ex.config.Hostname != nil {
		job.HostName = *ex.config.Hostname
	}

	var err error
	switch job.RepoType {
	case "remote":
		log.Trace(jctx, "Fetching git repository")
		if err = ex.prepareGit(jctx); err != nil {
			erCh <- gerrors.Wrap(err)
			return
		}
	case "local":
		log.Trace(jctx, "Fetching tar archive")
		if err = ex.prepareArchive(jctx); err != nil {
			erCh <- gerrors.Wrap(err)
			return
		}
	default:
		log.Error(jctx, "Unknown RepoType", "RepoType", job.RepoType)
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
				if err != nil {
					erCh <- gerrors.Wrap(err)
					return
				}
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
	dir := path.Join(ex.backend.GetTMPDir(ctx), consts.RUNS_DIR, job.RunName, job.JobID)
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

	repoDiff := ""
	if job.RepoCodeFilename != "" {
		var err error
		repoDiff, err = ex.backend.GetRepoDiff(ctx, job.RepoCodeFilename)
		if err != nil {
			return err
		}
	}
	if repoDiff != "" {
		if err := repo.ApplyDiff(ctx, dir, repoDiff); err != nil {
			return gerrors.Wrap(err)
		}
	}
	return nil
}

func (ex *Executor) prepareArchive(ctx context.Context) error {
	job := ex.backend.Job(ctx)
	dir := path.Join(ex.backend.GetTMPDir(ctx), consts.RUNS_DIR, job.RunName, job.JobID)
	if _, err := os.Stat(dir); err != nil {
		if err = os.MkdirAll(dir, 0777); err != nil {
			return gerrors.Wrap(err)
		}
	}
	if err := ex.backend.GetRepoArchive(ctx, job.RepoCodeFilename, dir); err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (ex *Executor) processDeps(ctx context.Context) error {
	job := ex.backend.Job(ctx)
	for _, dep := range job.Deps {
		listDir, err := ex.backend.ListSubDir(ctx, fmt.Sprintf("jobs/%s/%s,", dep.RepoId, dep.RunName))
		if err != nil {
			return gerrors.Wrap(err)
		}
		for _, pathJob := range listDir {
			jobDep, err := ex.backend.GetJobByPath(ctx, pathJob)
			if err != nil {
				return gerrors.Wrap(err)
			}
			for _, artifact := range jobDep.Artifacts {
				artIn := ex.backend.GetArtifact(ctx, jobDep.RunName, artifact.Path, path.Join("artifacts", jobDep.RepoId, jobDep.JobID, artifact.Path), artifact.Mount)
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
	for _, cache := range job.Cache {
		cacheArt := ex.backend.GetCache(ctx, job.RunName, cache.Path, path.Join("cache", job.RepoId, job.HubUserName, job.WorkflowName, cache.Path))
		if cacheArt != nil {
			ex.cacheArtifacts = append(ex.cacheArtifacts, cacheArt)
		}
	}
	return nil
}

func (ex *Executor) environment(ctx context.Context, includeRun bool) []string {
	log.Trace(ctx, "Start generate env")
	job := ex.backend.Job(ctx)
	env := environment.New()

	if includeRun {
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
		if job.MasterJobID != "" {
			master := ex.backend.MasterJob(ctx)
			cons["MASTER_ID"] = master.JobID
			cons["MASTER_HOSTNAME"] = master.HostName
			cons["MASTER_JOB_ID"] = master.JobID
			cons["MASTER_JOB_HOSTNAME"] = master.HostName
		}
		env.AddMapString(job.RunEnvironment)
		env.AddMapString(cons)
	}
	env.AddMapString(job.Environment)
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
		Source: path.Join(ex.backend.GetTMPDir(ctx), consts.RUNS_DIR, job.RunName, job.JobID),
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
	if job.RepoType == "remote" && job.HomeDir != "" {
		cred := ex.backend.GitCredentials(ctx)
		if cred != nil {
			log.Trace(ctx, "Trying to mount git credentials")
			credPath := path.Join(ex.backend.GetTMPDir(ctx), consts.RUNS_DIR, job.RunName, "credentials")
			credMountPath := ""
			switch cred.Protocol {
			case "ssh":
				if cred.PrivateKey != nil {
					credMountPath = path.Join(job.HomeDir, ".ssh/id_rsa")
					if err := os.WriteFile(credPath, []byte(*cred.PrivateKey), 0600); err != nil {
						log.Error(ctx, "Failed writing credentials", "err", err)
					}
				}
			case "https":
				if cred.OAuthToken != nil {
					credMountPath = path.Join(job.HomeDir, ".config/gh/hosts.yml")
					ghHost := fmt.Sprintf("%s:\n  oauth_token: \"%s\"\n", job.RepoHostName, *cred.OAuthToken)
					if err := os.WriteFile(credPath, []byte(ghHost), 0644); err != nil {
						log.Error(ctx, "Failed writing credentials", "err", err)
					}
				}
			default:
			}
			if credMountPath != "" {
				defer os.Remove(credPath)
				log.Trace(ctx, "Mounting git credentials", "target", credMountPath)
				bindings = append(bindings, mount.Mount{
					Type:   mount.TypeBind,
					Source: credPath,
					Target: credMountPath,
				})
			}
		}
	}
	logger := ex.backend.CreateLogger(ctx, fmt.Sprintf("/dstack/jobs/%s/%s", ex.backend.Bucket(ctx), job.RepoId), job.RunName)
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

	_, isLocalBackend := ex.backend.(*localbackend.Local)
	appsBindingPorts, err := ports.GetAppsBindingPorts(ctx, job.Apps, isLocalBackend)
	if err != nil {
		// todo custom exit status
		log.Error(ctx, "Failed binding ports", "err", err)
		return gerrors.Wrap(err)
	}
	if err = ex.backend.UpdateState(ctx); err != nil {
		return gerrors.Wrap(err)
	}

	spec := &container.Spec{
		Image:              job.Image,
		RegistryAuthBase64: makeRegistryAuthBase64(username, password),
		WorkDir:            path.Join("/workflow", job.WorkingDir),
		Commands:           container.ShellCommands(job.Commands),
		Entrypoint:         job.Entrypoint,
		Env:                ex.environment(ctx, true),
		Mounts:             uniqueMount(bindings),
		ExposedPorts:       ports.GetAppsExposedPorts(ctx, job.Apps, isLocalBackend),
		BindingPorts:       appsBindingPorts,
		ShmSize:            resource.ShmSize,
		AllowHostMode:      !isLocalBackend,
	}
	logGroup := fmt.Sprintf("/jobs/%s", job.RepoId)
	fileLog, err := createLocalLog(filepath.Join(ex.configDir, "logs", logGroup), job.RunName)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer fileLog.Close()

	ml := io.MultiWriter(logger, ex.streamLogs, fileLog)
	if err = ex.prebuild(ctx, spec, ml); err != nil {
		return gerrors.Wrap(err)
	}
	// todo change state to RUNNING
	docker, err := ex.engine.Create(ctx, spec, ml)
	if err != nil {
		return gerrors.Wrap(err)
	}
	err = docker.Run(ctx)
	if err != nil {
		return gerrors.Wrap(err)
	}
	errCh := make(chan error, 2) // err and nil
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

func (ex *Executor) prebuild(ctx context.Context, spec *container.Spec, logs io.Writer) error {
	job := ex.backend.Job(ctx)

	log.Trace(ctx, "Start prebuild", "mode", job.Prebuild)
	if job.Prebuild == models.NEVER_PREBUILD || len(job.Setup) == 0 {
		log.Trace(ctx, "Do not prebuild")
		commands := append([]string(nil), job.Setup...)
		commands = append(commands, job.Commands...)
		spec.Commands = container.ShellCommands(commands)
		return nil
	}

	prebuildSpec := &container.PrebuildSpec{
		BaseImageName:      spec.Image,
		WorkDir:            spec.WorkDir,
		Commands:           container.ShellCommands(job.Setup),
		Entrypoint:         spec.Entrypoint,
		Env:                ex.environment(ctx, false),
		RegistryAuthBase64: spec.RegistryAuthBase64,
		RepoPath:           path.Join(ex.backend.GetTMPDir(ctx), consts.RUNS_DIR, job.RunName, job.JobID),
	}
	prebuildName, err := ex.engine.GetPrebuildName(ctx, prebuildSpec)
	if err != nil {
		return gerrors.Wrap(err)
	}

	tempDir, err := os.MkdirTemp("", "prebuild")
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = os.RemoveAll(tempDir) }()
	diffPath := filepath.Join(tempDir, "layer.tar")
	key := fmt.Sprintf("prebuilds/%s/%s.tar", job.RepoId, prebuildName)
	imageName := fmt.Sprintf("dstackai/prebuild:%s", prebuildName)

	if job.Prebuild == models.LAZY_PREBUILD {
		log.Trace(ctx, "Trying to fetch prebuild layer", "key", key, "image", imageName)
		if err = ex.backend.GetPrebuildDiff(ctx, key, diffPath); err != nil {
			return gerrors.Wrap(err)
		}
	}
	put, err := ex.engine.Prebuild(ctx, prebuildSpec, imageName, diffPath, logs)
	if err != nil {
		return gerrors.Wrap(err)
	}
	if put {
		log.Trace(ctx, "Putting prebuild layer", "key", key, "image", imageName)
		if err = ex.backend.PutPrebuildDiff(ctx, diffPath, key); err != nil {
			return gerrors.Wrap(err)
		}
	}
	spec.Image = imageName

	return nil
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
