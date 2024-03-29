package consts

import "time"

const DstackDirPath string = ".dstack"

// Runner's log filenames
const RunnerDefaultLogFileName = "default.log"
const RunnerJobLogFileName = "job.log"
const RunnerLogFileName = "runner.log"

// Error-containing messages will be identified by this signature
const ExecutorFailedSignature = "Executor failed"

// GPU constants
const (
	NVIDIA_CUDA_IMAGE        = "dstackai/cuda:11.8.0-base-ubuntu20.04"
	NVIDIA_SMI_CMD           = "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader"
	NVIDIA_RUNTIME           = "nvidia"
	NVIDIA_DRIVER_INIT_ERROR = "stderr: nvidia-container-cli: initialization error: nvml error: driver not loaded: unknown"
)

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
