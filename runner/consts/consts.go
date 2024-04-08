package consts

import "time"

const DstackDirPath string = ".dstack"

// Runner's log filenames
const RunnerDefaultLogFileName = "default.log"
const RunnerJobLogFileName = "job.log"
const RunnerLogFileName = "runner.log"

// Error-containing messages will be identified by this signature
const ExecutorFailedSignature = "Executor failed"

const HostInfoFile = "host_info.json"

// GPU constants
const NVIDIA_RUNTIME = "nvidia"

// JOB ports
const (
	EXPOSE_PORT_START = 3000
	EXPOSE_PORT_END   = 4000
)

const MAX_ATTEMPTS = 10
const DELAY_TRY = 6 * time.Second

const DELAY_READ_STATUS = 5 * time.Second

const REPO_HTTPS_URL = "https://%s/%s/%s.git"
const REPO_GIT_URL = "git@%s:%s/%s.git"

const (
	TERMINATE_POLICY = "terminate"
	STOP_POLICY      = "stop"
)
