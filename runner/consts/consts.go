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

// A directory inside the container where runner stores its files (logs, etc.)
const RunnerDir = "/tmp/runner"
