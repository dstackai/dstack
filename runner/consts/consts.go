package consts

const DstackDirPath string = ".dstack"

// Runner's log filenames
const (
	RunnerDefaultLogFileName = "default.log"
	RunnerJobLogFileName     = "job.log"
	RunnerLogFileName        = "runner.log"
)

// 1. A fixed path inside the container
// 2. A default path on the host unless overridden via shim CLI
const RunnerBinaryPath = "/usr/local/bin/dstack-runner"

// A fallback path on the host used if os.Executable() has failed
const ShimBinaryPath = "/usr/local/bin/dstack-shim"

// Error-containing messages will be identified by this signature
const ExecutorFailedSignature = "Executor failed"

// All the following are directories inside the container
const (
	// A directory where runner stores its files (logs, etc.)
	// NOTE: RunnerRuntimeDir would be a more appropriate name, but it's called tempDir
	// throughout runner's codebase
	RunnerTempDir = "/tmp/runner"
	// Currently, it's a directory where authorized_keys, git credentials, etc. are placed
	// The current user's homedir (as of 2024-12-28, it's always root) should be used
	// instead of the hardcoded value
	RunnerHomeDir = "/root"
)

const (
	RunnerHTTPPort = 10999
	RunnerSSHPort  = 10022
)

const ShimLogFileName = "shim.log"
