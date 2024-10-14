package schemas

import "strings"

type JobStateEvent struct {
	State     string `json:"state"`
	Timestamp int64  `json:"timestamp"`
}

type LogEvent struct {
	Message   []byte `json:"message"`
	Timestamp int64  `json:"timestamp"`
}

type SubmitBody struct {
	RunSpec         RunSpec           `json:"run_spec"`
	JobSpec         JobSpec           `json:"job_spec"`
	ClusterInfo     ClusterInfo       `json:"cluster_info"`
	Secrets         map[string]string `json:"secrets"`
	RepoCredentials *RepoCredentials  `json:"repo_credentials"`
}

type PullResponse struct {
	JobStates   []JobStateEvent `json:"job_states"`
	JobLogs     []LogEvent      `json:"job_logs"`
	RunnerLogs  []LogEvent      `json:"runner_logs"`
	LastUpdated int64           `json:"last_updated"`
	HasMore     bool            `json:"has_more"`
	// todo Result
}

type RunSpec struct {
	RunName           string        `json:"run_name"`
	RepoId            string        `json:"repo_id"`
	RepoData          RepoData      `json:"repo_data"`
	Configuration     Configuration `json:"configuration"`
	ConfigurationPath string        `json:"configuration_path"`
}

type JobSpec struct {
	ReplicaNum     int               `json:"replica_num"`
	JobNum         int               `json:"job_num"`
	JobsPerReplica int               `json:"jobs_per_replica"`
	Commands       []string          `json:"commands"`
	Entrypoint     []string          `json:"entrypoint"`
	Env            map[string]string `json:"env"`
	Gateway        *Gateway          `json:"gateway"`
	MaxDuration    int               `json:"max_duration"`
	WorkingDir     *string           `json:"working_dir"`
}

type ClusterInfo struct {
	MasterJobIP string `json:"master_job_ip"`
	GPUSPerJob  int    `json:"gpus_per_job"`
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

type Configuration struct {
	Type string `json:"type"`
}

type Gateway struct {
	GatewayName string `json:"gateway_name"`
	ServicePort int    `json:"service_port"`
	SSHKey      string `json:"ssh_key"`
	SockPath    string `json:"sock_path"`
	Hostname    string `json:"hostname"`
	PublicPort  int    `json:"public_port"`
	Secure      bool   `json:"secure"`
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
