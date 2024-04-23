package consts

const DstackDirPath string = ".dstack"

// Runner's log filenames
const (
	RunnerDefaultLogFileName = "default.log"
	RunnerJobLogFileName     = "job.log"
	RunnerLogFileName        = "runner.log"
)

// Error-containing messages will be identified by this signature
const ExecutorFailedSignature = "Executor failed"

const HostInfoFile = "host_info.json"

// GPU constants
const NVIDIA_RUNTIME = "nvidia"

const (
	REPO_HTTPS_URL = "https://%s/%s/%s.git"
	REPO_GIT_URL   = "git@%s:%s/%s.git"
)
