package executor

import (
	"context"
	"github.com/dstackai/dstack/runner/consts/states"
	"github.com/dstackai/dstack/runner/internal/api"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"io"
	"os/exec"
	"path/filepath"
)

type Executor struct {
	server        *api.ServerAdapter
	workingDir    string
	jobLogsWriter io.Writer

	run             api.Run
	jobSpec         api.JobSpec
	secrets         map[string]string
	repoCredentials *api.RepoCredentials
	codePath        string
}

func NewExecutor(workingDir string, jobLogsWriter io.Writer, adapter *api.ServerAdapter) *Executor {
	return &Executor{
		server:        adapter,
		workingDir:    workingDir,
		jobLogsWriter: jobLogsWriter,
	}
}

func (ex *Executor) Run(ctx context.Context) error {
	select {
	case body := <-ex.server.GetJob():
		log.Debug(ctx, "Executor received a job")
		ex.run = body.Run
		ex.jobSpec = body.JobSpec
		ex.secrets = body.Secrets
		ex.repoCredentials = body.RepoCredentials
	case <-ctx.Done():
		ex.server.SetJobState(states.Terminated)
		return gerrors.New("executor was terminated before it received a job")
		// todo timeout
	}

	select {
	case codePath := <-ex.server.GetCode():
		log.Debug(ctx, "Executor received a code")
		ex.codePath = codePath
	case <-ctx.Done():
		ex.server.SetJobState(states.Terminated)
		return gerrors.New("executor was terminated before it received a code")
		// todo timeout
	}

	select {
	case <-ex.server.WaitRun():
		log.Debug(ctx, "Executor received a start signal")
	case <-ctx.Done():
		ex.server.SetJobState(states.Terminated)
		return gerrors.New("executor was terminated before it received a start signal")
		// todo timeout
	}

	if err := ex.setupRepo(ctx); err != nil {
		ex.server.SetJobState(states.Failed)
		return gerrors.Wrap(err)
	}
	cleanupCredentials, err := ex.setupCredentials(ctx)
	if err != nil {
		ex.server.SetJobState(states.Failed)
		return gerrors.Wrap(err)
	}
	defer cleanupCredentials()

	// todo artifacts in

	// todo gateway

	ex.server.SetJobState(states.Running)
	if err := ex.execJob(ctx); err != nil {
		// todo fail reason
		ex.server.SetJobState(states.Failed)
		return gerrors.Wrap(err)
	}

	// todo artifacts out

	ex.server.SetJobState(states.Done)
	return nil
}

func (ex *Executor) execJob(ctx context.Context) error {
	// todo recover
	args := makeArgs(ex.jobSpec.Entrypoint, ex.jobSpec.Commands)
	cmd := exec.CommandContext(ctx, ex.jobSpec.Entrypoint[0], args...)
	cmd.Env = makeEnv(ex.jobSpec.Env, ex.secrets)
	cmd.Dir = filepath.Join(ex.workingDir, ex.jobSpec.WorkingDir) // todo error on illegal path
	// todo call SIGINT in cmd.Cancel

	cmdReader, err := cmd.StdoutPipe()
	if err != nil {
		return gerrors.Wrap(err)
	}
	cmd.Stderr = cmd.Stdout // merge stderr into stdout

	if err := cmd.Start(); err != nil {
		return gerrors.Wrap(err)
	}
	if _, err := io.Copy(ex.jobLogsWriter, cmdReader); err != nil {
		return gerrors.Wrap(err)
	}
	return gerrors.Wrap(cmd.Wait())
}

func (ex *Executor) setupCredentials(ctx context.Context) (func(), error) {
	// todo
	return func() {}, nil
}
