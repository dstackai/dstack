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

// All the following are directories inside the container
const (
	// A directory where runner stores its files (logs, etc.)
	// NOTE: RunnerRuntimeDir would be a more appropriate name, but it's called tempDir
	// throughout runner's codebase
	RunnerTempDir = "/tmp/runner"
	// Currently, it's a directory where autorized_keys, git credentials, etc. are placed
	// The current user's homedir (as of 2024-12-28, it's always root) should be used
	// instead of the hardcoded value
	RunnerHomeDir = "/root"
	// A repo directory and a default working directory for the job
	RunnerWorkingDir = "/workflow"
)

const ShimLogFileName = "shim.log"
