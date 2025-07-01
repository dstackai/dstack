package schemas

import (
	"strings"

	"github.com/dstackai/dstack/runner/internal/types"
)

type JobStateEvent struct {
	State              types.JobState          `json:"state"`
	Timestamp          int64                   `json:"timestamp"`
	TerminationReason  types.TerminationReason `json:"termination_reason"`
	TerminationMessage string                  `json:"termination_message"`
	ExitStatus         *int                    `json:"exit_status"`
}

type LogEvent struct {
	Message   []byte `json:"message"`
	Timestamp int64  `json:"timestamp"`
}

type SubmitBody struct {
	Run             Run               `json:"run"`
	JobSpec         JobSpec           `json:"job_spec"`
	JobSubmission   JobSubmission     `json:"job_submission"`
	ClusterInfo     ClusterInfo       `json:"cluster_info"`
	Secrets         map[string]string `json:"secrets"`
	RepoCredentials *RepoCredentials  `json:"repo_credentials"`
}

type PullResponse struct {
	JobStates         []JobStateEvent `json:"job_states"`
	JobLogs           []LogEvent      `json:"job_logs"`
	RunnerLogs        []LogEvent      `json:"runner_logs"`
	LastUpdated       int64           `json:"last_updated"`
	NoConnectionsSecs int64           `json:"no_connections_secs"`
	HasMore           bool            `json:"has_more"`
	// todo Result
}

type Run struct {
	Id      string  `json:"id"`
	RunSpec RunSpec `json:"run_spec"`
}

type RunSpec struct {
	RunName           string        `json:"run_name"`
	RepoId            string        `json:"repo_id"`
	RepoData          RepoData      `json:"repo_data"`
	Configuration     Configuration `json:"configuration"`
	ConfigurationPath string        `json:"configuration_path"`
}

type JobSubmission struct {
	Id string `json:"id"`
}

type JobSpec struct {
	ReplicaNum     int               `json:"replica_num"`
	JobNum         int               `json:"job_num"`
	JobsPerReplica int               `json:"jobs_per_replica"`
	User           *User             `json:"user"`
	Commands       []string          `json:"commands"`
	Entrypoint     []string          `json:"entrypoint"`
	Env            map[string]string `json:"env"`
	SingleBranch   bool              `json:"single_branch"`
	MaxDuration    int               `json:"max_duration"`
	SSHKey         *SSHKey           `json:"ssh_key"`
	WorkingDir     *string           `json:"working_dir"`
	// `RepoData` is optional for compatibility with jobs submitted before 0.19.17.
	// Use `RunExecutor.getRepoData()` to get non-nil `RepoData`.
	// TODO: make required when supporting jobs submitted before 0.19.17 is no longer relevant.
	RepoData     *RepoData     `json:"repo_data"`
	FileArchives []FileArchive `json:"file_archives"`
}

type ClusterInfo struct {
	JobIPs      []string `json:"job_ips"`
	MasterJobIP string   `json:"master_job_ip"`
	GPUSPerJob  int      `json:"gpus_per_job"`
}

type SSHKey struct {
	Private string `json:"private"`
	Public  string `json:"public"`
}

type RepoCredentials struct {
	CloneURL   string  `json:"clone_url"`
	PrivateKey *string `json:"private_key"`
	OAuthToken *string `json:"oauth_token"`
}

type RepoData struct {
	RepoType string `json:"repo_type"`

	RepoBranch string `json:"repo_branch"`
	RepoHash   string `json:"repo_hash"`

	RepoConfigName  string `json:"repo_config_name"`
	RepoConfigEmail string `json:"repo_config_email"`
}

type FileArchive struct {
	Id   string `json:"id"`
	Path string `json:"path"`
}

type Configuration struct {
	Type string `json:"type"`
}

type User struct {
	Uid       *uint32 `json:"uid"`
	Username  *string `json:"username"`
	Gid       *uint32 `json:"gid"`
	Groupname *string `json:"groupname"`
	GroupIds  []uint32
	HomeDir   string
}

func (u *User) GetUsername() string {
	if u.Username == nil {
		return ""
	}
	return *u.Username
}

func (u *User) GetGroupname() string {
	if u.Groupname == nil {
		return ""
	}
	return *u.Groupname
}

type HealthcheckResponse struct {
	Service string `json:"service"`
	Version string `json:"version"`
}

type GPUMetrics struct {
	GPUMemoryUsage uint64 `json:"gpu_memory_usage_bytes"`
	GPUUtil        uint64 `json:"gpu_util_percent"`
}

type SystemMetrics struct {
	Timestamp        int64        `json:"timestamp_micro"`
	CpuUsage         uint64       `json:"cpu_usage_micro"`
	MemoryUsage      uint64       `json:"memory_usage_bytes"`
	MemoryWorkingSet uint64       `json:"memory_working_set_bytes"`
	GPUMetrics       []GPUMetrics `json:"gpus"`
}

func (c *RepoCredentials) GetProtocol() string {
	return strings.SplitN(c.CloneURL, "://", 2)[0]
}

func (e JobStateEvent) GetTimestamp() int64 {
	return e.Timestamp
}

func (e LogEvent) GetTimestamp() int64 {
	return e.Timestamp
}
