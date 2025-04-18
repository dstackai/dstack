package executor

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"net/url"
	"os"
	"os/exec"
	osuser "os/user"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/creack/pty"
	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/connections"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/schemas"
	"github.com/dstackai/dstack/runner/internal/types"
	"github.com/prometheus/procfs"
)

type RunExecutor struct {
	tempDir    string
	homeDir    string
	workingDir string
	sshPort    int
	uid        uint32

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

	killDelay         time.Duration
	connectionTracker *connections.ConnectionTracker
}

func NewRunExecutor(tempDir string, homeDir string, workingDir string, sshPort int) (*RunExecutor, error) {
	mu := &sync.RWMutex{}
	timestamp := NewMonotonicTimestamp()
	user, err := osuser.Current()
	if err != nil {
		return nil, fmt.Errorf("failed to get current user: %w", err)
	}
	uid, err := parseStringId(user.Uid)
	if err != nil {
		return nil, fmt.Errorf("failed to parse current user uid: %w", err)
	}
	proc, err := procfs.NewDefaultFS()
	if err != nil {
		return nil, fmt.Errorf("failed to initialize procfs: %w", err)
	}
	connectionTracker := connections.NewConnectionTracker(connections.ConnectionTrackerConfig{
		Port:            uint64(sshPort),
		MinConnDuration: 10 * time.Second, // shorter connections are likely from dstack-server
		Procfs:          proc,
	})
	return &RunExecutor{
		tempDir:    tempDir,
		homeDir:    homeDir,
		workingDir: workingDir,
		sshPort:    sshPort,
		uid:        uid,

		mu:              mu,
		state:           WaitSubmit,
		jobStateHistory: make([]schemas.JobStateEvent, 0),
		jobLogs:         newAppendWriter(mu, timestamp),
		runnerLogs:      newAppendWriter(mu, timestamp),
		timestamp:       timestamp,

		killDelay:         10 * time.Second,
		connectionTracker: connectionTracker,
	}, nil
}

// Run must be called after SetJob and SetCodePath
func (ex *RunExecutor) Run(ctx context.Context) (err error) {
	runnerLogFile, err := log.CreateAppendFile(filepath.Join(ex.tempDir, consts.RunnerLogFileName))
	if err != nil {
		ex.SetJobState(ctx, types.JobStateFailed)
		return gerrors.Wrap(err)
	}
	defer func() { _ = runnerLogFile.Close() }()

	jobLogFile, err := log.CreateAppendFile(filepath.Join(ex.tempDir, consts.RunnerJobLogFileName))
	if err != nil {
		ex.SetJobState(ctx, types.JobStateFailed)
		return gerrors.Wrap(err)
	}
	defer func() { _ = jobLogFile.Close() }()

	defer func() {
		// recover goes after runnerLogFile.Close() to keep the log
		if r := recover(); r != nil {
			log.Error(ctx, "Executor PANIC", "err", r)
			ex.SetJobState(ctx, types.JobStateFailed)
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
		ex.SetJobStateWithTerminationReason(
			ctx,
			types.JobStateFailed,
			types.TerminationReasonContainerExitedWithError,
			fmt.Sprintf("Failed to set up the repo (%s)", err),
		)
		return gerrors.Wrap(err)
	}
	cleanupCredentials, err := ex.setupCredentials(ctx)
	if err != nil {
		ex.SetJobState(ctx, types.JobStateFailed)
		return gerrors.Wrap(err)
	}
	defer cleanupCredentials()

	connectionTrackerTicker := time.NewTicker(2500 * time.Millisecond)
	go ex.connectionTracker.Track(connectionTrackerTicker.C)
	defer ex.connectionTracker.Stop()

	ex.SetJobState(ctx, types.JobStateRunning)
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
			ex.SetJobState(ctx, types.JobStateTerminated)
			return gerrors.Wrap(err)
		default:
		}

		select {
		case <-timeoutCtx.Done():
			log.Error(ctx, "Max duration exceeded", "max_duration", ex.jobSpec.MaxDuration)
			ex.SetJobStateWithTerminationReason(
				ctx,
				types.JobStateTerminated,
				types.TerminationReasonMaxDurationExceeded,
				"Max duration exceeded",
			)
			return gerrors.Wrap(err)
		default:
		}

		// todo fail reason?
		log.Error(ctx, "Exec failed", "err", err)
		ex.SetJobState(ctx, types.JobStateFailed)
		return gerrors.Wrap(err)
	}

	ex.SetJobState(ctx, types.JobStateDone)
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

func (ex *RunExecutor) SetJobState(ctx context.Context, state types.JobState) {
	ex.SetJobStateWithTerminationReason(ctx, state, "", "")
}

func (ex *RunExecutor) SetJobStateWithTerminationReason(
	ctx context.Context, state types.JobState, termination_reason types.TerminationReason, termination_message string,
) {
	ex.mu.Lock()
	ex.jobStateHistory = append(
		ex.jobStateHistory,
		schemas.JobStateEvent{
			State:              state,
			Timestamp:          ex.timestamp.Next(),
			TerminationReason:  termination_reason,
			TerminationMessage: termination_message,
		},
	)
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
		log.Info(ctx, "New LD_LIBRARY_PATH set", "LD_LIBRARY_PATH", newLDPath)
	}

	cmd := exec.CommandContext(ctx, ex.jobSpec.Commands[0], ex.jobSpec.Commands[1:]...)
	cmd.Cancel = func() error {
		// returns error on Windows
		return gerrors.Wrap(cmd.Process.Signal(os.Interrupt))
	}
	cmd.WaitDelay = ex.killDelay // kills the process if it doesn't exit in time

	cmd.Dir = ex.workingDir
	if ex.jobSpec.WorkingDir != nil {
		workingDir, err := joinRelPath(ex.workingDir, *ex.jobSpec.WorkingDir)
		if err != nil {
			return gerrors.Wrap(err)
		}
		cmd.Dir = workingDir
	}

	user := ex.jobSpec.User
	if user != nil {
		if err := fillUser(user); err != nil {
			return gerrors.Wrap(err)
		}
		log.Trace(
			ctx, "Using credentials",
			"uid", *user.Uid, "gid", *user.Gid, "groups", user.GroupIds,
			"username", user.GetUsername(), "groupname", user.GetGroupname(),
			"home", user.HomeDir,
		)
		log.Trace(ctx, "Current user", "uid", ex.uid)

		// 1. Ideally, We should check uid, gid, and supplementary groups mismatches,
		// but, for the sake of simplicity, we only check uid. Unprivileged runner
		// should not receive job requests where user credentials do not match the
		// current user's ones in the first place (it should be handled by the server)
		// 2. Strictly speaking, we need CAP_SETUID and CAP_GUID (for Cmd.Start()->
		// Cmd.SysProcAttr.Credential) and CAP_CHOWN (for startCommand()->os.Chown()),
		// but for the sake of simplicity we instead check if we are root or not
		if *user.Uid != ex.uid && ex.uid != 0 {
			return gerrors.Newf("cannot start job as %d, current uid is %d", *user.Uid, ex.uid)
		}

		if cmd.SysProcAttr == nil {
			cmd.SysProcAttr = &syscall.SysProcAttr{}
		}
		// It's safe to setuid(2)/setgid(2)/setgroups(2) as unprivileged user if we use
		// user's own credentials (basically, it's noop)
		cmd.SysProcAttr.Credential = &syscall.Credential{
			Uid:    *user.Uid,
			Gid:    *user.Gid,
			Groups: user.GroupIds,
		}
	}

	envMap := NewEnvMap(ParseEnvList(os.Environ()), jobEnvs, ex.secrets)
	// `env` interpolation feature is postponed to some future release
	envMap.Update(ex.jobSpec.Env, false)

	const profilePath = "/etc/profile"
	const dstackProfilePath = "/tmp/dstack_profile"
	if err := writeDstackProfile(envMap, dstackProfilePath); err != nil {
		log.Warning(ctx, "failed to write dstack_profile", "path", dstackProfilePath, "err", err)
	} else if err := includeDstackProfile(profilePath, dstackProfilePath); err != nil {
		log.Warning(ctx, "failed to include dstack_profile", "path", profilePath, "err", err)
	}

	// As of 2024-11-29, ex.homeDir is always set to /root
	rootSSHDir, err := prepareSSHDir(-1, -1, ex.homeDir)
	if err != nil {
		log.Warning(ctx, "failed to prepare ssh dir", "home", ex.homeDir, "err", err)
	}
	userSSHDir := ""
	uid := -1
	gid := -1
	if user != nil && *user.Uid != 0 {
		// non-root user
		uid = int(*user.Uid)
		gid = int(*user.Gid)
		homeDir, isHomeDirAccessible := prepareHomeDir(ctx, uid, gid, user.HomeDir)
		envMap["HOME"] = homeDir
		if isHomeDirAccessible {
			log.Trace(ctx, "provisioning homeDir", "path", homeDir)
			userSSHDir, err = prepareSSHDir(uid, gid, homeDir)
			if err != nil {
				log.Warning(ctx, "failed to prepare ssh dir", "home", homeDir, "err", err)
			} else {
				rootSSHKeysPath := filepath.Join(rootSSHDir, "authorized_keys")
				userSSHKeysPath := filepath.Join(userSSHDir, "authorized_keys")
				restoreUserSSHKeys := backupFile(ctx, userSSHKeysPath)
				defer restoreUserSSHKeys(ctx)
				if err := copyAuthorizedKeys(rootSSHKeysPath, uid, gid, userSSHKeysPath); err != nil {
					log.Warning(ctx, "failed to copy authorized keys", "path", homeDir, "err", err)
				}
			}
		} else {
			log.Trace(ctx, "homeDir is not accessible, skipping provisioning", "path", homeDir)
		}
	} else {
		// root user
		envMap["HOME"] = ex.homeDir
		userSSHDir = filepath.Join(ex.homeDir, ".ssh")
	}

	if ex.jobSpec.SSHKey != nil && userSSHDir != "" {
		err := configureSSH(
			ex.jobSpec.SSHKey.Private, ex.jobSpec.SSHKey.Public, ex.clusterInfo.JobIPs, ex.sshPort,
			uid, gid, userSSHDir,
		)
		if err != nil {
			log.Warning(ctx, "failed to configure SSH", "err", err)
		}
	}

	cmd.Env = envMap.Render()

	log.Trace(ctx, "Starting exec", "cmd", cmd.String(), "working_dir", cmd.Dir, "env", cmd.Env)

	ptm, err := startCommand(cmd)
	if err != nil {
		return gerrors.Wrap(err)
	}
	defer func() { _ = ptm.Close() }()
	defer func() { _ = cmd.Wait() }() // release resources if copy fails

	logger := io.MultiWriter(jobLogFile, ex.jobLogs)
	_, err = io.Copy(logger, ptm)
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

// fillUser fills missing User fields
// Since normally only one kind of identifier is set (either id or name), we don't check
// (id, name) pair consistency -- id has higher priority and overwites name with a real
// name, ignoring the already set name value (if any)
// HomeDir and SupplementaryGroupIds are always set unconditionally, as they are not
// provided by the dstack server
func fillUser(user *schemas.User) error {
	if user.Uid == nil && user.Username == nil {
		return errors.New("neither Uid nor Username is set")
	}

	if user.Gid == nil && user.Groupname != nil {
		osGroup, err := osuser.LookupGroup(*user.Groupname)
		if err != nil {
			return fmt.Errorf("failed to look up group by Groupname: %w", err)
		}
		gid, err := parseStringId(osGroup.Gid)
		if err != nil {
			return fmt.Errorf("failed to parse group Gid: %w", err)
		}
		user.Gid = &gid
	}

	var osUser *osuser.User

	if user.Uid == nil {
		var err error
		osUser, err = osuser.Lookup(*user.Username)
		if err != nil {
			return fmt.Errorf("failed to look up user by Username: %w", err)
		}
		uid, err := parseStringId(osUser.Uid)
		if err != nil {
			return fmt.Errorf("failed to parse Uid: %w", err)
		}
		user.Uid = &uid
	} else {
		var err error
		osUser, err = osuser.LookupId(strconv.Itoa(int(*user.Uid)))
		if err != nil {
			var notFoundErr osuser.UnknownUserIdError
			if !errors.As(err, &notFoundErr) {
				return fmt.Errorf("failed to look up user by Uid: %w", err)
			}
		}
	}

	if osUser != nil {
		user.Username = &osUser.Username
		user.HomeDir = osUser.HomeDir
	} else {
		user.Username = nil
		user.HomeDir = ""
	}

	// If Gid is not set, either directly or via Groupname, use user's primary group
	// and supplementary groups, see https://docs.docker.com/reference/dockerfile/#user
	// If user doesn't exist, set Gid to 0 and supplementary groups to an empty list
	if user.Gid == nil {
		if osUser != nil {
			gid, err := parseStringId(osUser.Gid)
			if err != nil {
				return fmt.Errorf("failed to parse primary Gid: %w", err)
			}
			user.Gid = &gid
			groupStringIds, err := osUser.GroupIds()
			if err != nil {
				return fmt.Errorf("failed to get supplementary groups: %w", err)
			}
			var groupIds []uint32
			for _, groupStringId := range groupStringIds {
				groupId, err := parseStringId(groupStringId)
				if err != nil {
					return fmt.Errorf("failed to parse supplementary group id: %w", err)
				}
				groupIds = append(groupIds, groupId)
			}
			user.GroupIds = groupIds
		} else {
			var fallbackGid uint32 = 0
			user.Gid = &fallbackGid
			user.GroupIds = []uint32{}
		}
	}
	return nil
}

func parseStringId(stringId string) (uint32, error) {
	id, err := strconv.ParseInt(stringId, 10, 32)
	if err != nil {
		return 0, err
	}
	if id < 0 {
		return 0, fmt.Errorf("negative value: %d", id)
	}
	return uint32(id), nil
}

// A simplified copypasta of creack/pty Start->StartWithSize->StartWithAttrs
// with two additions:
// * controlling terminal is properly set (cmd.Extrafiles, Cmd.SysProcAttr.Ctty)
// * owner of slave pty is changed to the child process uid
func startCommand(cmd *exec.Cmd) (*os.File, error) {
	ptm, pts, err := pty.Open()
	if err != nil {
		return nil, err
	}
	defer func() { _ = pts.Close() }()

	cmd.Stdout = pts
	cmd.Stderr = pts
	cmd.Stdin = pts
	cmd.ExtraFiles = []*os.File{pts}
	if cmd.SysProcAttr == nil {
		cmd.SysProcAttr = &syscall.SysProcAttr{}
	}
	// see https://github.com/creack/pty/issues/96#issuecomment-624372400
	cmd.SysProcAttr.Ctty = 3 // cmd.ExtraFiles[0]
	cmd.SysProcAttr.Setctty = true
	cmd.SysProcAttr.Setsid = true

	if cmd.SysProcAttr.Credential != nil {
		// Initially, /dev/pts/N is owned by the user who open()'ed /dev/ptmx (runner_uid)
		// If the runner started by root, we can chown to any user
		// If the runner started by non-root, we can chown only to the same user (noop)
		// In the latter case, the situation when runner_uid != 0 and
		// runner_uid != job_uid should be already handled outside this function
		uid := cmd.SysProcAttr.Credential.Uid
		if err := os.Chown(pts.Name(), int(uid), -1); err != nil {
			_ = ptm.Close()
			return nil, err
		}
	}

	if err := cmd.Start(); err != nil {
		_ = ptm.Close()
		return nil, err
	}
	return ptm, nil
}

func prepareHomeDir(ctx context.Context, uid int, gid int, homeDir string) (string, bool) {
	if homeDir == "" {
		// user does not exist
		return "/", false
	}
	if info, err := os.Stat(homeDir); errors.Is(err, os.ErrNotExist) {
		if strings.Contains(homeDir, "nonexistent") {
			// let `/nonexistent` stay non-existent
			return homeDir, false
		}
		if err = os.MkdirAll(homeDir, 0o755); err != nil {
			log.Warning(ctx, "failed to create homeDir", "err", err)
			return homeDir, false
		}
		if err = os.Chmod(homeDir, 0o750); err != nil {
			log.Warning(ctx, "failed to chmod homeDir", "err", err)
		}
		if err = os.Chown(homeDir, uid, gid); err != nil {
			log.Warning(ctx, "failed to chown homeDir", "err", err)
		}
		return homeDir, true
	} else if err != nil {
		log.Warning(ctx, "homeDir is not accessible", "err", err)
		return homeDir, false
	} else if !info.IsDir() {
		log.Warning(ctx, "HomeDir is not a dir", "path", homeDir)
		return homeDir, false
	}
	return homeDir, true
}

func prepareSSHDir(uid int, gid int, homeDir string) (string, error) {
	sshDir := filepath.Join(homeDir, ".ssh")
	info, err := os.Stat(sshDir)
	if err == nil {
		if !info.IsDir() {
			return "", fmt.Errorf("not a directory: %s", sshDir)
		}
		if err = os.Chmod(sshDir, 0o700); err != nil {
			return "", err
		}
	} else if errors.Is(err, os.ErrNotExist) {
		if err = os.MkdirAll(sshDir, 0o700); err != nil {
			return "", err
		}
	} else {
		return "", err
	}
	if err = os.Chown(sshDir, uid, gid); err != nil {
		return "", err
	}
	return sshDir, nil
}

func writeDstackProfile(env map[string]string, path string) error {
	file, err := os.OpenFile(path, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	defer file.Close()
	for key, value := range env {
		switch key {
		case "HOSTNAME", "USER", "HOME", "SHELL", "SHLVL", "PWD", "_":
			continue
		}
		line := fmt.Sprintf("export %s='%s'\n", key, strings.ReplaceAll(value, `'`, `'"'"'`))
		if _, err = file.WriteString(line); err != nil {
			return err
		}
	}
	if err = os.Chmod(path, 0o644); err != nil {
		return err
	}
	return nil
}

func includeDstackProfile(profilePath string, dstackProfilePath string) error {
	file, err := os.OpenFile(profilePath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	defer file.Close()
	if _, err = file.WriteString(fmt.Sprintf("\n. '%s'\n", dstackProfilePath)); err != nil {
		return err
	}
	if err = os.Chmod(profilePath, 0o644); err != nil {
		return err
	}
	return nil
}

func configureSSH(private string, public string, ips []string, port int, uid int, gid int, sshDir string) error {
	privatePath := filepath.Join(sshDir, "dstack_job")
	privateFile, err := os.OpenFile(privatePath, os.O_TRUNC|os.O_WRONLY|os.O_CREATE, 0o600)
	if err != nil {
		return err
	}
	defer privateFile.Close()
	if err := os.Chown(privatePath, uid, gid); err != nil {
		return err
	}
	if _, err := privateFile.WriteString(private); err != nil {
		return err
	}

	akPath := filepath.Join(sshDir, "authorized_keys")
	akFile, err := os.OpenFile(akPath, os.O_APPEND|os.O_WRONLY|os.O_CREATE, 0o600)
	if err != nil {
		return err
	}
	defer akFile.Close()
	if err := os.Chown(akPath, uid, gid); err != nil {
		return err
	}
	if _, err := akFile.WriteString(public); err != nil {
		return err
	}

	configPath := filepath.Join(sshDir, "config")
	configFile, err := os.OpenFile(configPath, os.O_APPEND|os.O_WRONLY|os.O_CREATE, 0o600)
	if err != nil {
		return err
	}
	defer configFile.Close()
	if err := os.Chown(configPath, uid, gid); err != nil {
		return err
	}
	var configBuffer bytes.Buffer
	for _, ip := range ips {
		configBuffer.WriteString(fmt.Sprintf("\nHost %s\n", ip))
		configBuffer.WriteString(fmt.Sprintf("    Port %d\n", port))
		configBuffer.WriteString("    StrictHostKeyChecking no\n")
		configBuffer.WriteString("    UserKnownHostsFile /dev/null\n")
		configBuffer.WriteString(fmt.Sprintf("    IdentityFile %s\n", privatePath))
	}
	if _, err := configFile.Write(configBuffer.Bytes()); err != nil {
		return err
	}
	return nil
}

// A makeshift solution to deliver authorized_keys to a non-root user
// without modifying the existing API/bootstrap process
// TODO: implement key delivery properly, i.e. sumbit keys to and write by the runner,
// not the outer sh script that launches sshd and runner
func copyAuthorizedKeys(srcPath string, uid int, gid int, dstPath string) error {
	srcFile, err := os.Open(srcPath)
	if err != nil {
		return err
	}
	defer srcFile.Close()

	dstExists := false
	info, err := os.Stat(dstPath)
	if err == nil {
		dstExists = true
		if info.IsDir() {
			return fmt.Errorf("is a directory: %s", dstPath)
		}
		if err = os.Chmod(dstPath, 0o600); err != nil {
			return err
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return err
	}

	dstFile, err := os.OpenFile(dstPath, os.O_APPEND|os.O_WRONLY|os.O_CREATE, 0o600)
	if err != nil {
		return err
	}
	defer dstFile.Close()

	if dstExists {
		// visually separate our keys from existing ones
		if _, err := dstFile.WriteString("\n\n"); err != nil {
			return err
		}
	}
	if _, err := io.Copy(dstFile, srcFile); err != nil {
		return err
	}
	if err = os.Chown(dstPath, uid, gid); err != nil {
		return err
	}

	return nil
}

// backupFile renames `/path/to/file` to `/path/to/file.dstack.bak`,
// creates a new file with the same content, and returns restore function that
// renames the backup back to the original name.
// If the original file does not exist, restore function removes the file if it is created.
// NB: A newly created file has default uid:gid and permissions, probably not
// the same as the original file.
func backupFile(ctx context.Context, path string) func(context.Context) {
	var existed bool
	backupPath := path + ".dstack.bak"

	restoreFunc := func(ctx context.Context) {
		if !existed {
			err := os.Remove(path)
			if err != nil && !errors.Is(err, os.ErrNotExist) {
				log.Error(ctx, "failed to remove", "path", path, "err", err)
			}
			return
		}
		err := os.Rename(backupPath, path)
		if err != nil && !errors.Is(err, os.ErrNotExist) {
			log.Error(ctx, "failed to restore", "path", path, "err", err)
		}
	}

	err := os.Rename(path, backupPath)
	if errors.Is(err, os.ErrNotExist) {
		existed = false
		return restoreFunc
	}
	existed = true
	if err != nil {
		log.Error(ctx, "failed to back up", "path", path, "err", err)
		return restoreFunc
	}

	src, err := os.Open(backupPath)
	if err != nil {
		log.Error(ctx, "failed to open backup src", "path", backupPath, "err", err)
		return restoreFunc
	}
	defer src.Close()
	dst, err := os.Create(path)
	if err != nil {
		log.Error(ctx, "failed to open backup dest", "path", path, "err", err)
		return restoreFunc
	}
	defer dst.Close()
	_, err = io.Copy(dst, src)
	if err != nil {
		log.Error(ctx, "failed to copy backup", "path", backupPath, "err", err)
	}
	return restoreFunc
}
