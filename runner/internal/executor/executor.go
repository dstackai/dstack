package executor

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path"
	"path/filepath"
	"strconv"
	"time"

	"github.com/docker/go-connections/nat"
	"github.com/dstackai/dstack/runner/internal/gateway"

	"github.com/dstackai/dstack/runner/internal/backend/base"

	"github.com/dstackai/dstack/runner/internal/models"
	"github.com/dustin/go-humanize"

	localbackend "github.com/dstackai/dstack/runner/internal/backend/local"

	"github.com/docker/docker/api/types"

	"github.com/docker/docker/api/types/mount"
	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/consts/errorcodes"
	"github.com/dstackai/dstack/runner/consts/states"
	"github.com/dstackai/dstack/runner/internal/backend"
	"github.com/dstackai/dstack/runner/internal/docker"
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
	engine         *docker.Engine
	cacheArtifacts []base.Artifacter
	artifactsIn    []base.Artifacter
	artifactsOut   []base.Artifacter
	artifactsFUSE  []base.Artifacter
	repo           *repo.Manager
	streamLogs     *stream.Server
	stoppedCh      chan bool
}

func New(b backend.Backend) *Executor {
	return &Executor{
		backend:   b,
		engine:    docker.NewEngine(),
		stoppedCh: make(chan bool),
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
		artOut := ex.backend.GetArtifact(ctx, job.RunName, artifact.Path, path.Join("artifacts", job.RepoRef.RepoId, job.JobID, artifact.Path), artifact.Mount)
		if artOut != nil {
			ex.artifactsOut = append(ex.artifactsOut, artOut)
		}
		if artifact.Mount {
			art := ex.backend.GetArtifact(ctx, job.RunName, artifact.Path, path.Join("artifacts", job.RepoRef.RepoId, job.JobID, artifact.Path), artifact.Mount)
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
			job, _ := ex.backend.RefetchJob(runCtx)
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
			job, err := ex.backend.RefetchJob(runCtx)
			if err != nil {
				return gerrors.Wrap(err)
			}
			if job.MaxDurationExceeded() {
				log.Info(runCtx, "Job max duration exceeded")
				if job.TerminationPolicy == consts.STOP_POLICY {
					job.Status = states.Stopping
				} else {
					job.Status = states.Terminating
				}
			}
			if job.Status == states.Stopping {
				log.Info(runCtx, "Stopped")
				ex.Stop(false)
				log.Info(runCtx, "Waiting job end")
				errRun := <-erCh
				job.Status = states.Stopped
				_ = ex.backend.UpdateState(runCtx)
				return errRun
			} else if job.Status == states.Terminating {
				log.Info(runCtx, "Terminated")
				ex.Stop(true)
				log.Info(runCtx, "Waiting job end")
				errRun := <-erCh
				job.Status = states.Terminated
				_ = ex.backend.UpdateState(runCtx)
				return errRun
			}
		case <-ctx.Done():
			log.Info(runCtx, "Terminated")
			ex.Stop(true)
			log.Info(runCtx, "Waiting job end")
			errRun := <-erCh
			job, err := ex.backend.RefetchJob(runCtx)
			if err != nil {
				return gerrors.Wrap(err)
			}
			job.Status = states.Terminated
			_ = ex.backend.UpdateState(runCtx)
			return errRun
		case errRun := <-erCh:
			job, err := ex.backend.RefetchJob(runCtx)
			if err != nil {
				return gerrors.Wrap(err)
			}
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
				containerExitedError := &docker.ContainerExitedError{}
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

func (ex *Executor) Stop(remove bool) {
	select {
	case <-ex.stoppedCh:
		return
	default:
	}
	ex.stoppedCh <- remove
	close(ex.stoppedCh)
}

func (ex *Executor) Shutdown(ctx context.Context) {
	defer func() {
		if r := recover(); r != nil {
			log.Error(ctx, "[PANIC]", "", r)
			panic(r)
		}
	}()
	job := ex.backend.Job(ctx)
	if job.Status == states.Stopped {
		err := ex.backend.Stop(ctx)
		if err != nil {
			log.Error(ctx, "Shutdown", "err", err)
		}
		return
	}
	err := ex.backend.Shutdown(ctx)
	if err != nil {
		log.Error(ctx, "Shutdown", "err", err)
	}
}

func (ex *Executor) runJob(ctx context.Context, erCh chan error, stoppedCh chan bool) {
	job := ex.backend.Job(ctx)
	jctx := log.AppendArgsCtx(ctx,
		"run_name", job.RunName,
		"job_id", job.JobID,
		"configuration", job.ConfigurationPath,
	)
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

	logger := ex.backend.CreateLogger(ctx, fmt.Sprintf("/dstack/jobs/%s/%s", ex.backend.Bucket(ctx), job.RepoRef.RepoId), job.RunName)
	logGroup := fmt.Sprintf("/jobs/%s", job.RepoRef.RepoId)
	fileLog, err := createLocalLog(filepath.Join(ex.configDir, "logs", logGroup), job.RunName)
	if err != nil {
		erCh <- gerrors.Wrap(err)
		return
	}
	defer func() { _ = fileLog.Close() }()
	allLogs := io.MultiWriter(logger, ex.streamLogs, fileLog)

	if job.Status == states.Restarting {
		log.Info(jctx, "Restarting job")
		ex.restartJob(jctx, erCh, stoppedCh, allLogs)
	} else {
		log.Info(jctx, "Starting job", "job_id")
		ex.startJob(jctx, erCh, stoppedCh, allLogs)
	}
}

func (ex *Executor) startJob(ctx context.Context, erCh chan error, stoppedCh chan bool, allLogs io.Writer) {
	job := ex.backend.Job(ctx)

	if ex.config.Hostname != nil {
		job.HostName = *ex.config.Hostname
	}

	var err error
	switch job.RepoData.RepoType {
	case "remote":
		log.Trace(ctx, "Fetching git repository")
		if err = ex.prepareGit(ctx); err != nil {
			erCh <- gerrors.Wrap(err)
			return
		}
	case "local":
		log.Trace(ctx, "Fetching tar archive")
		if err = ex.prepareArchive(ctx); err != nil {
			erCh <- gerrors.Wrap(err)
			return
		}
	default:
		log.Error(ctx, "Unknown RepoType", "RepoType", job.RepoData.RepoType)
	}

	if job.BuildPolicy != models.BuildOnly {
		log.Trace(ctx, "Dependency processing")
		if err = ex.processCache(ctx); err != nil {
			erCh <- gerrors.Wrap(err)
			return
		}
		if err = ex.processDeps(ctx); err != nil {
			erCh <- gerrors.Wrap(err)
			return
		}
		for _, artifact := range ex.artifactsFUSE {
			err = artifact.BeforeRun(ctx)
			if err != nil {
				erCh <- gerrors.Wrap(err)
				return
			}
		}
		if len(ex.artifactsIn) > 0 || len(ex.cacheArtifacts) > 0 {
			log.Trace(ctx, "Start downloading artifacts")
			job.Status = states.Downloading
			err = ex.backend.UpdateState(ctx)
			if err != nil {
				erCh <- gerrors.Wrap(err)
				return
			}
			for _, artifact := range ex.artifactsIn {
				err = artifact.BeforeRun(ctx)
				if err != nil {
					erCh <- gerrors.Wrap(err)
					return
				}
			}
			for _, artifact := range ex.cacheArtifacts {
				err = artifact.BeforeRun(ctx)
				if err != nil {
					erCh <- gerrors.Wrap(err)
					return
				}
			}
		}
	}

	credPath := path.Join(ex.backend.GetTMPDir(ctx), consts.RUNS_DIR, job.RunName, "credentials")
	spec, err := ex.newSpec(ctx, credPath)
	if err != nil {
		erCh <- gerrors.Wrap(err)
		return
	}
	defer func() { // cleanup credentials
		_ = os.Remove(credPath)
	}()

	log.Trace(ctx, "Building container", "mode", job.BuildPolicy)
	job.Status = states.Building
	if err = ex.backend.UpdateState(ctx); err != nil {
		erCh <- gerrors.Wrap(err)
		return
	}
	if err = ex.build(ctx, spec, stoppedCh, allLogs); err != nil {
		erCh <- gerrors.Wrap(err)
		return
	}

	if job.BuildPolicy == models.BuildOnly {
		log.Trace(ctx, "Build only, do not run the job")
		ex.streamLogs.Close()
		erCh <- nil
		return
	}

	log.Trace(ctx, "Running job")
	job.Status = states.Running
	if err = ex.backend.UpdateState(ctx); err != nil {
		erCh <- gerrors.Wrap(err)
		return
	}

	var gatewayControl *gateway.SSHControl
	if job.ConfigurationType == "service" {
		binding, ok := spec.BindingPorts[nat.Port(fmt.Sprintf("%d/tcp", job.Gateway.ServicePort))]
		if !ok {
			erCh <- gerrors.Newf("gateway: job doesn't expose port %d", job.Gateway.ServicePort)
			return
		}
		localPort := binding[0].HostPort
		gatewayControl, err = gateway.NewSSHControl(job.Gateway.Hostname, job.Gateway.SSHKey)
		if err != nil {
			erCh <- gerrors.Wrap(err)
			return
		}
		defer gatewayControl.Cleanup()
		if err := gatewayControl.Publish(localPort, job.Gateway.SockPath); err != nil {
			erCh <- gerrors.Wrap(err)
			return
		}
	}

	container, err := ex.engine.CreateNamed(ctx, spec, job.InstanceName, allLogs)
	if err != nil {
		erCh <- gerrors.Wrap(err)
		return
	}
	if err = ex.runContainer(ctx, container, stoppedCh); err != nil {
		erCh <- gerrors.Wrap(err)
		return
	}

	ex.uploadArtifacts(ctx, erCh)
	erCh <- nil
}

func (ex *Executor) restartJob(ctx context.Context, erCh chan error, stoppedCh chan bool, allLogs io.Writer) {
	job := ex.backend.Job(ctx)
	log.Trace(ctx, "Running job")
	job.Status = states.Running
	if err := ex.backend.UpdateState(ctx); err != nil {
		erCh <- gerrors.Wrap(err)
		return
	}

	container, err := ex.engine.Get(ctx, job.RunName, allLogs)
	if err != nil {
		erCh <- gerrors.Wrap(err)
		return
	}
	if err = ex.runContainer(ctx, container, stoppedCh); err != nil {
		erCh <- gerrors.Wrap(err)
		return
	}

	ex.uploadArtifacts(ctx, erCh)
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
	ex.repo = repo.NewManager(ctx, fmt.Sprintf(consts.REPO_HTTPS_URL, job.RepoHostNameWithPort(), job.RepoData.RepoUserName, job.RepoData.RepoName), job.RepoData.RepoBranch, job.RepoData.RepoHash).WithLocalPath(dir)
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
			ex.repo = repo.NewManager(ctx, fmt.Sprintf(consts.REPO_GIT_URL, job.RepoHostNameWithPort(), job.RepoData.RepoUserName, job.RepoData.RepoName), job.RepoData.RepoBranch, job.RepoData.RepoHash).WithLocalPath(dir)
			ex.repo.WithSSHAuth(*cred.PrivateKey, password)
		default:
			log.Error(ctx, "Unsupported protocol", "protocol", cred.Protocol)
		}
	}

	if err := ex.repo.Checkout(); err != nil {
		log.Trace(ctx, "GIT checkout error", "err", err, "GIT URL", ex.repo.URL())
		return gerrors.Wrap(err)
	}
	if err := ex.repo.SetConfig(job.RepoData.RepoConfigName, job.RepoData.RepoConfigEmail); err != nil {
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
				artIn := ex.backend.GetArtifact(ctx, jobDep.RunName, artifact.Path, path.Join("artifacts", jobDep.RepoRef.RepoId, jobDep.JobID, artifact.Path), artifact.Mount)
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
		cacheArt := ex.backend.GetCache(ctx, job.RunName, cache.Path, path.Join("cache", job.RepoRef.RepoId, job.HubUserName, models.EscapeHead(job.ConfigurationPath), cache.Path))
		if cacheArt != nil {
			ex.cacheArtifacts = append(ex.cacheArtifacts, cacheArt)
		}
	}
	return nil
}

func (ex *Executor) newSpec(ctx context.Context, credPath string) (*docker.Spec, error) {
	job := ex.backend.Job(ctx)
	resource := ex.backend.Requirements(ctx)

	bindings := make([]mount.Mount, 0)
	bindings = append(bindings, mount.Mount{
		Type:   mount.TypeBind,
		Source: path.Join(ex.backend.GetTMPDir(ctx), consts.RUNS_DIR, job.RunName, job.JobID),
		Target: "/workflow",
	})
	bindings = append(bindings, mount.Mount{
		Type:   mount.TypeBind,
		Source: filepath.Join(ex.configDir, consts.CONFIG_FILE_NAME),
		Target: filepath.Join(job.HomeDir, ".dstack", consts.CONFIG_FILE_NAME),
	})
	bindings = append(bindings, ex.backend.GetDockerBindings(ctx)...)

	for _, artifact := range ex.artifactsIn {
		art, err := artifact.DockerBindings(path.Join("/workflow", job.WorkingDir))
		if err != nil {
			return nil, gerrors.Wrap(err)
		}
		bindings = append(bindings, art...)
	}
	for _, artifact := range ex.artifactsOut {
		art, err := artifact.DockerBindings(path.Join("/workflow", job.WorkingDir))
		if err != nil {
			return nil, gerrors.Wrap(err)
		}
		bindings = append(bindings, art...)
	}
	for _, artifact := range ex.cacheArtifacts {
		art, err := artifact.DockerBindings(path.Join("/workflow", job.WorkingDir))
		if err != nil {
			return nil, gerrors.Wrap(err)
		}
		bindings = append(bindings, art...)
	}
	if job.RepoData.RepoType == "remote" && job.HomeDir != "" {
		cred := ex.backend.GitCredentials(ctx)
		if cred != nil {
			log.Trace(ctx, "Trying to mount git credentials")
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
					ghHost := fmt.Sprintf("%s:\n  oauth_token: \"%s\"\n", job.RepoData.RepoHostName, *cred.OAuthToken)
					if err := os.WriteFile(credPath, []byte(ghHost), 0644); err != nil {
						log.Error(ctx, "Failed writing credentials", "err", err)
					}
				}
			default:
			}
			if credMountPath != "" {
				log.Trace(ctx, "Mounting git credentials", "target", credMountPath)
				bindings = append(bindings, mount.Mount{
					Type:   mount.TypeBind,
					Source: credPath,
					Target: credMountPath,
				})
			}
		}
	}

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
		log.Error(ctx, "Failed binding ports", "err", err)
		job.ErrorCode = errorcodes.PortsBindingFailed
		_ = ex.backend.UpdateState(ctx)
		return nil, gerrors.Wrap(err)
	}
	if err = ex.backend.UpdateState(ctx); err != nil {
		return nil, gerrors.Wrap(err)
	}

	commands := buildSetupCommands(job.Setup)
	commands = append(commands, job.Commands...)

	spec := &docker.Spec{
		Image:              job.Image,
		RegistryAuthBase64: makeRegistryAuthBase64(username, password),
		WorkDir:            path.Join("/workflow", job.WorkingDir),
		Commands:           docker.ShellCommands(docker.InsertEnvs(commands, job.Environment)),
		Entrypoint:         job.Entrypoint,
		Env:                ex.environment(ctx, true),
		Mounts:             uniqueMount(bindings),
		ExposedPorts:       ports.GetAppsExposedPorts(ctx, job.Apps, isLocalBackend),
		BindingPorts:       appsBindingPorts,
		ShmSize:            resource.ShmSize,
		AllowHostMode:      !isLocalBackend,
	}
	return spec, nil
}

func (ex *Executor) environment(ctx context.Context, includeRun bool) []string {
	log.Trace(ctx, "Start generate env")
	job := ex.backend.Job(ctx)
	env := environment.New()

	if includeRun {
		cons := make(map[string]string)
		cons["PYTHONUNBUFFERED"] = "1"
		cons["DSTACK_REPO"] = job.RepoRef.RepoId
		cons["JOB_ID"] = job.JobID

		cons["RUN_NAME"] = job.RunName

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
		env.AddMapString(cons)
	}
	secrets, err := ex.backend.Secrets(ctx)
	if err != nil {
		log.Error(ctx, "Fail fetching secrets", "err", err)
	}
	env.AddMapString(secrets)

	log.Trace(ctx, "Stop generate env", "slice", env.ToSlice())
	return env.ToSlice()
}

func buildSetupCommands(setup []string) []string {
	if len(setup) == 0 {
		return []string{}
	}
	joinedSetupCommands := docker.ShellCommands(setup)[0]
	dstackDir := filepath.Join("~", consts.DSTACK_DIR_PATH)
	setupCompletedFilepath := filepath.Join(dstackDir, consts.SETUP_COMPLETED_FILE_NAME)
	res := []string{
		fmt.Sprintf(
			"([ -f %s ] || (%s && mkdir -p %s &&  touch %s))",
			setupCompletedFilepath,
			joinedSetupCommands,
			dstackDir,
			setupCompletedFilepath,
		),
	}
	return res
}

func (ex *Executor) runContainer(ctx context.Context, container *docker.Container, stoppedCh chan bool) error {
	err := container.Run(ctx)
	if err != nil {
		return gerrors.Wrap(err)
	}
	errCh := make(chan error, 2) // err and nil
	go func() {
		defer func() {
			ex.streamLogs.Close()
			log.Info(ctx, "Docker log stream closed")
		}()
		err = container.Wait(ctx)
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
	case remove := <-stoppedCh:
		err = container.Stop(ctx, remove)
		if err != nil {
			return gerrors.Wrap(err)
		}
		return nil
	}
}

func (ex *Executor) build(ctx context.Context, spec *docker.Spec, stoppedCh chan bool, logs io.Writer) error {
	job := ex.backend.Job(ctx)
	if len(job.BuildCommands) == 0 {
		return nil
	}
	secrets, err := ex.backend.Secrets(ctx)
	if err != nil {
		return gerrors.Wrap(err)
	}
	buildSpec, err := ex.engine.NewBuildSpec(ctx, job, spec, secrets, path.Join(ex.backend.GetTMPDir(ctx), consts.RUNS_DIR, job.RunName, job.JobID), logs)
	if err != nil {
		return gerrors.Wrap(err)
	}
	imageName := fmt.Sprintf("dstackai/build:%s", buildSpec.Hash())
	_, isLocalBackend := ex.backend.(*localbackend.Local)
	diffPath, err := os.CreateTemp("", "layer*.tar")
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = os.Remove(diffPath.Name()) }()

	if job.BuildPolicy == models.UseBuild || job.BuildPolicy == models.Build {
		buildInfo, err := ex.backend.GetBuildDiffInfo(ctx, buildSpec)
		if err == nil {
			if isLocalBackend {
				if exists, err := ex.engine.ImageExists(ctx, imageName); err != nil {
					return gerrors.Wrap(err)
				} else if exists {
					_, _ = fmt.Fprintf(ex.streamLogs, "The image is loaded\n")
					spec.Image = imageName
					return nil
				}
				err = gerrors.Wrap(base.ErrBuildNotFound)
			} else {
				_, _ = fmt.Fprintf(ex.streamLogs, "Downloading the image diff (%s)...\n", humanize.Bytes(uint64(buildInfo.Size)))
				if err := ex.backend.GetBuildDiff(ctx, buildInfo.Key, diffPath.Name()); err != nil {
					return gerrors.Wrap(err)
				}
				_, _ = fmt.Fprintf(ex.streamLogs, "Loading the image diff...\n")
				if err := ex.engine.ImportImageDiff(ctx, diffPath.Name()); err != nil {
					return gerrors.Wrap(err)
				}
				_, _ = fmt.Fprintf(ex.streamLogs, "The image is loaded\n")
				spec.Image = imageName
				return nil
			}
		} else if !errors.Is(err, base.ErrBuildNotFound) {
			return gerrors.Wrap(err)
		}
		// handle ErrBuildNotFound
		if len(job.BuildCommands) > 0 { // if build is not optional
			_, _ = fmt.Fprintf(ex.streamLogs, "No image is found\n")
			if job.BuildPolicy == models.UseBuild {
				job.ErrorCode = errorcodes.BuildNotFound
				_ = ex.backend.UpdateState(ctx)
				return gerrors.Wrap(err)
			}
		}
	}

	if job.BuildPolicy == models.Build || job.BuildPolicy == models.ForceBuild || job.BuildPolicy == models.BuildOnly {
		if err := ex.engine.Build(ctx, buildSpec, imageName, stoppedCh, logs); err != nil {
			return gerrors.Wrap(err)
		}
		// local backend: store image in daemon cache, put empty diff as head file
		if !isLocalBackend {
			_, _ = fmt.Fprintf(ex.streamLogs, "Saving the image diff...\n")
			if err := ex.engine.ExportImageDiff(ctx, imageName, diffPath.Name()); err != nil {
				return gerrors.Wrap(err)
			}
			diffStat, err := os.Stat(diffPath.Name())
			if err != nil {
				return gerrors.Wrap(err)
			}
			log.Trace(ctx, "Putting build image diff", "image", imageName, "size", diffStat.Size())
			_, _ = fmt.Fprintf(ex.streamLogs, "Uploading the image diff (%s)...\n", humanize.Bytes(uint64(diffStat.Size())))
		}
		if err := ex.backend.PutBuildDiff(ctx, diffPath.Name(), buildSpec); err != nil {
			return gerrors.Wrap(err)
		}
		_, _ = fmt.Fprintf(ex.streamLogs, "The image diff is saved\n")
		spec.Image = imageName
	}

	return nil
}

func (ex *Executor) uploadArtifacts(ctx context.Context, erCh chan error) {
	job := ex.backend.Job(ctx)
	if len(ex.artifactsOut) > 0 || len(ex.cacheArtifacts) > 0 {
		log.Trace(ctx, "Start uploading artifacts")
		job.Status = states.Uploading
		err := ex.backend.UpdateState(ctx)
		if err != nil {
			erCh <- gerrors.Wrap(err)
			return
		}
		for _, artifact := range ex.artifactsOut {
			err = artifact.AfterRun(ctx)
			if err != nil {
				erCh <- gerrors.Wrap(err)
				return
			}
		}
		for _, artifact := range ex.cacheArtifacts {
			err = artifact.AfterRun(ctx)
			if err != nil {
				erCh <- gerrors.Wrap(err)
				return
			}
		}
	}
	for _, artifact := range ex.artifactsFUSE {
		err := artifact.AfterRun(ctx)
		if err != nil {
			erCh <- gerrors.Wrap(err)
			return
		}
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
