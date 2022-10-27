package consts

import "time"

const DSTACK_DIR_PATH string = ".dstack"
const CONFIG_FILE_NAME string = "config.yaml"
const RUNNER_FILE_NAME string = "runner.yaml"
const TMP_DIR_PATH = DSTACK_DIR_PATH + "/tmp"
const USER_ARTIFACTS_PATH = TMP_DIR_PATH + "/user_artifacts"
const FUSE_PATH = TMP_DIR_PATH + "/fuse"
const RUNS_PATH = TMP_DIR_PATH + "/runs"

const FILE_LOCK_FULL_DOWNLOAD = ".lock.full"

// ServerUrl A default build-time variable. The value is overridden via ldflags.
var ServerUrl = "https://api.stgn.dstack.ai"

//var ServerUrl = "https://api.dstack.ai"

// GPU constants
const (
	NVIDIA_CUDA_IMAGE        = "dstackai/cuda:11.1-base-ubuntu20.04"
	NVIDIA_SMI_CMD           = "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader"
	NVIDIA_RUNTIME           = "nvidia"
	NVIDIA_DRIVER_INIT_ERROR = "stderr: nvidia-container-cli: initialization error: nvml error: driver not loaded: unknown"
)

//JOB ports
const (
	EXPOSE_PORT_START = 3000
	EXPOSE_PORT_END   = 4000
)

const MAX_ATTEMPTS = 10
const DELAY_TRY = 6 * time.Second

const DELAY_READ_STATUS = 5 * time.Second

const REPO_HTTPS_URL = "https://github.com/%s/%s.git"
const REPO_GIT_URL = "git@github.com:%s/%s.git"
