package executor

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/creack/pty"
	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/consts/states"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/schemas"
)

type RunExecutor struct {
	tempDir    string
	homeDir    string
	workingDir string

	run             schemas.RunSpec
	jobSpec         schemas.JobSpec
	clusterInfo     schemas.ClusterInfo
	secrets         map[string]string
	repoCredentials *schemas.RepoCredentials
	codePath        string

	mu              *sync.RWMutex
	state           string
	jobStateHistory []schemas.JobStateEvent
	jobLogs         *appendWriter
	runnerLogs      *appendWriter
	timestamp       *MonotonicTimestamp

	killDelay time.Duration
}

func NewRunExecutor(tempDir string, homeDir string, workingDir string) *RunExecutor {
	mu := &sync.RWMutex{}
	timestamp := NewMonotonicTimestamp()
	return &RunExecutor{
		tempDir:    tempDir,
		homeDir:    homeDir,
		workingDir: workingDir,

		mu:              mu,
		state:           WaitSubmit,
		jobStateHistory: make([]schemas.JobStateEvent, 0),
		jobLogs:         newAppendWriter(mu, timestamp),
		runnerLogs:      newAppendWriter(mu, timestamp),
		timestamp:       timestamp,

		killDelay: 10 * time.Second,
	}
}

// Run must be called after SetJob and SetCodePath
func (ex *RunExecutor) Run(ctx context.Context) (err error) {
	runnerLogFile, err := log.CreateAppendFile(filepath.Join(ex.tempDir, consts.RunnerLogFileName))
	if err != nil {
		ex.SetJobState(ctx, states.Failed)
		return gerrors.Wrap(err)
	}
	defer func() { _ = runnerLogFile.Close() }()

	jobLogFile, err := log.CreateAppendFile(filepath.Join(ex.tempDir, consts.RunnerJobLogFileName))
	if err != nil {
		ex.SetJobState(ctx, states.Failed)
		return gerrors.Wrap(err)
	}
	defer func() { _ = jobLogFile.Close() }()

	defer func() {
		// recover goes after runnerLogFile.Close() to keep the log
		if r := recover(); r != nil {
			log.Error(ctx, "Executor PANIC", "err", r)
			ex.SetJobState(ctx, states.Failed)
			err = gerrors.Newf("recovered: %v", r)
		}
		// no more logs will be written after this
		ex.mu.Lock()
		ex.SetRunnerState(WaitLogsFinished)
		ex.mu.Unlock()
	}()
	defer func() {
		if err != nil {
			// TODO: refactor error handling and logs
			log.Error(ctx, consts.ExecutorFailedSignature, "err", err)
		}
	}()

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

	// var gatewayControl *gateway.SSHControl
	//if ex.run.Configuration.Type == "service" {
	//	log.Info(ctx, "Forwarding service port to the gateway", "hostname", ex.jobSpec.Gateway.Hostname)
	//	gatewayControl, err = gateway.NewSSHControl(ex.jobSpec.Gateway.Hostname, ex.jobSpec.Gateway.SSHKey)
	//	if err != nil {
	//		ex.SetJobState(ctx, states.Failed)
	//		return gerrors.Wrap(err)
	//	}
	//	defer gatewayControl.Cleanup()
	//	if err = gatewayControl.Publish(strconv.Itoa(ex.jobSpec.Gateway.ServicePort), ex.jobSpec.Gateway.SockPath); err != nil {
	//		ex.SetJobState(ctx, states.Failed)
	//		return gerrors.Wrap(err)
	//	}
	//	log.Info(ctx, "SSH tunnel established", "sock_path", ex.jobSpec.Gateway.SockPath, "service_port", ex.jobSpec.Gateway.ServicePort)
	//}

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
		log.Error(ctx, "Exec failed", "err", err)
		ex.SetJobState(ctx, states.Failed)
		return gerrors.Wrap(err)
	}

	ex.SetJobState(ctx, states.Done)
	return nil
}

func (ex *RunExecutor) SetJob(body schemas.SubmitBody) {
	ex.run = body.RunSpec
	ex.jobSpec = body.JobSpec
	ex.clusterInfo = body.ClusterInfo
	ex.secrets = body.Secrets
	ex.repoCredentials = body.RepoCredentials
	ex.state = WaitCode
}

func (ex *RunExecutor) SetCodePath(codePath string) {
	ex.codePath = codePath
	ex.state = WaitRun
}

func (ex *RunExecutor) SetJobState(ctx context.Context, state string) {
	ex.mu.Lock()
	ex.jobStateHistory = append(ex.jobStateHistory, schemas.JobStateEvent{State: state, Timestamp: ex.timestamp.Next()})
	ex.mu.Unlock()
	log.Info(ctx, "Job state changed", "new", state)
}

func (ex *RunExecutor) SetRunnerState(state string) {
	ex.state = state
}

func (ex *RunExecutor) execJob(ctx context.Context, jobLogFile io.Writer) error {
	node_rank := ex.jobSpec.JobNum
	nodes_num := ex.jobSpec.JobsPerReplica
	gpus_per_node_num := ex.clusterInfo.GPUSPerJob
	gpus_num := nodes_num * gpus_per_node_num

	jobEnvs := map[string]string{
		"RUN_NAME":              ex.run.RunName, // deprecated, remove in 0.19
		"REPO_ID":               ex.run.RepoId,  // deprecated, remove in 0.19
		"DSTACK_RUN_NAME":       ex.run.RunName,
		"DSTACK_REPO_ID":        ex.run.RepoId,
		"DSTACK_NODES_IPS":      strings.Join(ex.clusterInfo.JobIPs, "\n"),
		"DSTACK_MASTER_NODE_IP": ex.clusterInfo.MasterJobIP,
		"DSTACK_NODE_RANK":      strconv.Itoa(node_rank),
		"DSTACK_NODES_NUM":      strconv.Itoa(nodes_num),
		"DSTACK_GPUS_PER_NODE":  strconv.Itoa(gpus_per_node_num),
		"DSTACK_GPUS_NUM":       strconv.Itoa(gpus_num),
	}

	// Call buildLDLibraryPathEnv and update jobEnvs if no error occurs
	newLDPath, err := buildLDLibraryPathEnv()
	if err != nil {
		log.Info(ctx, "Continuing without updating LD_LIBRARY_PATH")
	} else {
		jobEnvs["LD_LIBRARY_PATH"] = newLDPath
		log.Info(ctx, "New LD_LIBRARY_PATH set", newLDPath)
	}

	cmd := exec.CommandContext(ctx, ex.jobSpec.Commands[0], ex.jobSpec.Commands[1:]...)
	cmd.Env = makeEnv(ex.homeDir, jobEnvs, ex.jobSpec.Env, ex.secrets)
	cmd.Cancel = func() error {
		// returns error on Windows
		return gerrors.Wrap(cmd.Process.Signal(os.Interrupt))
	}
	cmd.WaitDelay = ex.killDelay // kills the process if it doesn't exit in time

	if ex.jobSpec.WorkingDir != nil {
		workingDir, err := joinRelPath(ex.workingDir, *ex.jobSpec.WorkingDir)
		if err != nil {
			return gerrors.Wrap(err)
		}
		cmd.Dir = workingDir
	}

	log.Trace(ctx, "Starting exec", "cmd", cmd.String(), "working_dir", cmd.Dir, "env", cmd.Env)

	ptmx, err := pty.Start(cmd)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = ptmx.Close() }()
	defer func() { _ = cmd.Wait() }() // release resources if copy fails

	logger := io.MultiWriter(jobLogFile, ex.jobLogs)
	_, err = io.Copy(logger, ptmx)
	if err != nil && !isPtyError(err) {
		return gerrors.Wrap(err)
	}
	return gerrors.Wrap(cmd.Wait())
}

func (ex *RunExecutor) setupCredentials(ctx context.Context) (func(), error) {
	if ex.repoCredentials == nil {
		return func() {}, nil
	}
	switch ex.repoCredentials.GetProtocol() {
	case "ssh":
		if ex.repoCredentials.PrivateKey == nil {
			return nil, gerrors.New("private key is missing")
		}
		keyPath := filepath.Join(ex.homeDir, ".ssh/id_rsa")
		if _, err := os.Stat(keyPath); err == nil {
			return nil, gerrors.New("private key already exists")
		}
		if err := os.MkdirAll(filepath.Dir(keyPath), 0o700); err != nil {
			return nil, gerrors.Wrap(err)
		}
		log.Info(ctx, "Writing private key", "path", keyPath)
		if err := os.WriteFile(keyPath, []byte(*ex.repoCredentials.PrivateKey), 0o600); err != nil {
			return nil, gerrors.Wrap(err)
		}
		return func() {
			log.Info(ctx, "Removing private key", "path", keyPath)
			_ = os.Remove(keyPath)
		}, nil
	case "https":
		if ex.repoCredentials.OAuthToken == nil {
			return func() {}, nil
		}
		hostsPath := filepath.Join(ex.homeDir, ".config/gh/hosts.yml")
		if _, err := os.Stat(hostsPath); err == nil {
			return nil, gerrors.New("hosts.yml file already exists")
		}
		if err := os.MkdirAll(filepath.Dir(hostsPath), 0o700); err != nil {
			return nil, gerrors.Wrap(err)
		}
		log.Info(ctx, "Writing OAuth token", "path", hostsPath)
		cloneURL, err := url.Parse(ex.repoCredentials.CloneURL)
		if err != nil {
			return nil, gerrors.Wrap(err)
		}
		ghHost := fmt.Sprintf("%s:\n  oauth_token: \"%s\"\n", cloneURL.Hostname(), *ex.repoCredentials.OAuthToken)
		if err := os.WriteFile(hostsPath, []byte(ghHost), 0o600); err != nil {
			return nil, gerrors.Wrap(err)
		}
		return func() {
			log.Info(ctx, "Removing OAuth token", "path", hostsPath)
			_ = os.Remove(hostsPath)
		}, nil
	}
	return nil, gerrors.Newf("unknown protocol %s", ex.repoCredentials.GetProtocol())
}

func isPtyError(err error) bool {
	/* read /dev/ptmx: input/output error */
	var e *os.PathError
	return errors.As(err, &e) && errors.Is(e.Err, syscall.EIO)
}

func buildLDLibraryPathEnv() (string, error) {
	// Execute shell command to get Python prefix
	cmd := exec.Command("bash", "-i", "-c", "python3-config --prefix")
	output, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("error executing command: %w", err)
	}

	// Extract and trim the prefix path
	prefixPath := strings.TrimSpace(string(output))

	// Check if the prefix path exists
	if _, err := os.Stat(prefixPath); os.IsNotExist(err) {
		return "", fmt.Errorf("python prefix path does not exist: %s", prefixPath)
	}

	// Construct the path to Python's shared libraries
	sharedLibPath := fmt.Sprintf("%s/lib", prefixPath)

	// Get current LD_LIBRARY_PATH
	currentLDPath := os.Getenv("LD_LIBRARY_PATH")

	// Append Python's shared library path if not already present
	if !strings.Contains(currentLDPath, sharedLibPath) {
		if currentLDPath == "" {
			currentLDPath = sharedLibPath
		} else {
			currentLDPath = fmt.Sprintf("%s:%s", currentLDPath, sharedLibPath)
		}
	}

	return currentLDPath, nil
}
