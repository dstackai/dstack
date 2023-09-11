package executor

import (
	"context"
	"github.com/dstackai/dstack/runner/consts/states"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/schemas"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"time"
)

type Executor struct {
	tempDir    string
	workingDir string

	run             schemas.Run
	jobSpec         schemas.JobSpec
	secrets         map[string]string
	repoCredentials *schemas.RepoCredentials
	codePath        string

	mu              *sync.RWMutex
	state           string
	jobStateHistory []schemas.JobStateEvent
	jobLogs         *appendWriter
	runnerLogs      *appendWriter
	timestamp       *MonotonicTimestamp
}

func NewExecutor(tempDir string, workingDir string) *Executor {
	mu := &sync.RWMutex{}
	timestamp := NewMonotonicTimestamp()
	return &Executor{
		tempDir:    tempDir,
		workingDir: workingDir,

		mu:              mu,
		state:           WaitSubmit,
		jobStateHistory: make([]schemas.JobStateEvent, 0),
		jobLogs:         newAppendWriter(mu, timestamp),
		runnerLogs:      newAppendWriter(mu, timestamp),
		timestamp:       timestamp,
	}
}

// Run must be called after SetJob and SetCodePath
func (ex *Executor) Run(ctx context.Context) error {
	runnerLogFile, err := log.CreateAppendFile(filepath.Join(ex.tempDir, "runner.log"))
	if err != nil {
		ex.SetJobState(ctx, states.Failed)
		return gerrors.Wrap(err)
	}
	defer func() { _ = runnerLogFile.Close() }()

	jobLogFile, err := log.CreateAppendFile(filepath.Join(ex.tempDir, "job.log"))
	if err != nil {
		ex.SetJobState(ctx, states.Failed)
		return gerrors.Wrap(err)
	}
	defer func() { _ = jobLogFile.Close() }()

	logger := io.MultiWriter(runnerLogFile, os.Stdout, ex.runnerLogs)
	ctx = log.WithLogger(ctx, log.NewEntry(logger, int(log.DefaultEntry.Logger.Level))) // todo loglevel
	log.Info(ctx, "Run job", "log_level", log.GetLogger(ctx).Logger.Level.String())

	if err := ex.setupRepo(ctx); err != nil {
		ex.SetJobState(ctx, states.Failed)
		return gerrors.Wrap(err)
	}
	cleanupCredentials, err := ex.setupCredentials(ctx)
	if err != nil {
		ex.SetJobState(ctx, states.Failed)
		return gerrors.Wrap(err)
	}
	defer cleanupCredentials()

	// todo gateway

	ex.SetJobState(ctx, states.Running)
	timeoutCtx := ctx
	var cancelTimeout context.CancelFunc
	if ex.jobSpec.MaxDuration != 0 {
		timeoutCtx, cancelTimeout = context.WithTimeout(ctx, time.Duration(ex.jobSpec.MaxDuration)*time.Second)
		defer cancelTimeout()
	}
	if err := ex.execJob(timeoutCtx, jobLogFile); err != nil {
		select {
		case <-ctx.Done():
			log.Error(ctx, "Job canceled")
			ex.SetJobState(ctx, states.Terminated)
			return gerrors.Wrap(err)
		default:
		}

		select {
		case <-timeoutCtx.Done():
			log.Error(ctx, "Max duration exceeded", "max_duration", ex.jobSpec.MaxDuration)
			ex.SetJobState(ctx, states.Terminated)
			return gerrors.Wrap(err)
		default:
		}

		// todo fail reason?
		ex.SetJobState(ctx, states.Failed)
	}

	ex.SetJobState(ctx, states.Done)
	return nil
}

func (ex *Executor) SetJob(body schemas.SubmitBody) {
	ex.run = body.Run
	ex.jobSpec = body.JobSpec
	ex.secrets = body.Secrets
	ex.repoCredentials = body.RepoCredentials
	ex.state = WaitCode
}

func (ex *Executor) SetCodePath(codePath string) {
	ex.codePath = codePath
	ex.state = WaitRun
}

func (ex *Executor) SetJobState(ctx context.Context, state string) {
	ex.mu.Lock()
	ex.jobStateHistory = append(ex.jobStateHistory, schemas.JobStateEvent{State: state, Timestamp: ex.timestamp.Next()})
	ex.mu.Unlock()
	log.Info(ctx, "Job state changed", "new", state)
}

func (ex *Executor) SetRunnerState(state string) {
	ex.state = state
}

func (ex *Executor) execJob(ctx context.Context, jobLogFile io.Writer) error {
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
	logger := io.MultiWriter(jobLogFile, ex.jobLogs)
	if _, err := io.Copy(logger, cmdReader); err != nil {
		return gerrors.Wrap(err)
	}
	return gerrors.Wrap(cmd.Wait())
}

func (ex *Executor) setupCredentials(ctx context.Context) (func(), error) {
	// todo
	return func() {}, nil
}
