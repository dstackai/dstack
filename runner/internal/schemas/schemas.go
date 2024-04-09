package schemas

import "fmt"

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
	WorkingDir     string            `json:"working_dir"`
}

type ClusterInfo struct {
	MasterJobIP string `json:"master_job_ip"`
	GPUSPerJob  int    `json:"gpus_per_job"`
}

type RepoCredentials struct {
	Protocol   string  `json:"protocol"`
	PrivateKey *string `json:"private_key"`
	OAuthToken *string `json:"oauth_token"`
}

type RepoData struct {
	RepoType     string `json:"repo_type"`
	RepoHostName string `json:"repo_host_name"`
	RepoPort     int    `json:"repo_port"`
	RepoUserName string `json:"repo_user_name"`
	RepoName     string `json:"repo_name"`

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

func (d *RepoData) FormatURL(format string) string {
	host := d.RepoHostName
	if d.RepoPort != 0 {
		host = fmt.Sprintf("%s:%d", d.RepoHostName, d.RepoPort)
	}
	return fmt.Sprintf(format, host, d.RepoUserName, d.RepoName)
}

func (e JobStateEvent) GetTimestamp() int64 {
	return e.Timestamp
}

func (e LogEvent) GetTimestamp() int64 {
	return e.Timestamp
}
