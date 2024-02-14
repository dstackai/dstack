package consts

import "time"

const (
	DSTACK_DIR_PATH    string = ".dstack"
	CONFIG_FILE_NAME   string = "backend.yaml"
	RUNNER_FILE_NAME   string = "runner.yaml"
	TMP_DIR_PATH              = DSTACK_DIR_PATH + "/tmp"
	USER_ARTIFACTS_DIR        = "artifacts"
	FUSE_DIR                  = "fuse"
	RUNS_DIR                  = "runs"
)

const (
	FILE_LOCK_FULL_DOWNLOAD   = ".lock.full"
	SETUP_COMPLETED_FILE_NAME = ".setup_completed"
)

// ServerUrl A default build-time variable. The value is overridden via ldflags.
var ServerUrl = "https://api.stgn.dstack.ai"

// var ServerUrl = "https://api.dstack.ai"

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

const (
	MAX_ATTEMPTS = 10
	DELAY_TRY    = 6 * time.Second
)

const DELAY_READ_STATUS = 5 * time.Second

const (
	REPO_HTTPS_URL = "https://%s/%s/%s.git"
	REPO_GIT_URL   = "git@%s:%s/%s.git"
)

const (
	TERMINATE_POLICY = "terminate"
	STOP_POLICY      = "stop"
)
