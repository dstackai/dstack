package models

type Resource struct {
	CPUs          int    `yaml:"cpus,omitempty"`
	Memory        uint64 `yaml:"memory_mib,omitempty"`
	GPUs          []GPU  `yaml:"gpus,omitempty"`
	Interruptible bool   `yaml:"interruptible,omitempty"`
	ShmSize       int64  `yaml:"shm_size_mib,omitempty"`
	Local         bool   `json:"local"`
}

type Job struct {
	Apps         []App                  `yaml:"apps"`
	Artifacts    []Artifact             `yaml:"artifacts"`
	Commands     []string               `yaml:"commands"`
	Environment  map[string]string      `yaml:"env"`
	HostName     string                 `yaml:"host_name"`
	Image        string                 `yaml:"image_name"`
	JobID        string                 `yaml:"job_id"`
	MasterJobID  string                 `yaml:"master_job_id"`
	PortCount    int                    `yaml:"port_count"`
	Ports        []string               `yaml:"ports"`
	Deps         []Dep                  `yaml:"deps"`
	ProviderName string                 `yaml:"provider_name"`
	RepoBranch   string                 `yaml:"repo_branch"`
	RepoDiff     string                 `yaml:"repo_diff"`
	RepoHash     string                 `yaml:"repo_hash"`
	RepoName     string                 `yaml:"repo_name"`
	RepoUserName string                 `yaml:"repo_user_name"`
	RequestID    string                 `yaml:"request_id"`
	Requirements Requirements           `yaml:"requirements"`
	RunName      string                 `yaml:"run_name"`
	RunnerID     string                 `yaml:"runner_id"`
	Status       string                 `yaml:"status"`
	SubmittedAt  uint64                 `yaml:"submitted_at"`
	TagName      string                 `yaml:"tag_name"`
	Variables    map[string]interface{} `yaml:"variables"`
	WorkflowName string                 `yaml:"workflow_name"`
	WorkingDir   string                 `yaml:"working_dir"`
}

type Dep struct {
	RepoUserName string `yaml:"repo_user_name,omitempty"`
	RepoName     string `yaml:"repo_name,omitempty"`
	RunName      string `yaml:"run_name,omitempty"`
	Mount        bool   `yaml:"mount,omitempty"`
}

type Artifact struct {
	Path  string `yaml:"path,omitempty"`
	Mount bool   `yaml:"mount,omitempty"`
}

type App struct {
	Name           string            `yaml:"app_name"`
	PortIdx        int               `yaml:"port_index"`
	UrlPath        string            `yaml:"url_path"`
	UrlQueryParams map[string]string `yaml:"url_query_params"`
}

type Requirements struct {
	GPUs          GPU   `yaml:"gpus,omitempty"`
	CPUs          int   `yaml:"cpus,omitempty"`
	Memory        int   `yaml:"memory_mib,omitempty"`
	Interruptible bool  `yaml:"interruptible,omitempty"`
	ShmSize       int64 `yaml:"shm_size_mib,omitempty"`
	Local         bool  `json:"local"`
}

type GPU struct {
	Count     int    `yaml:"count,omitempty"`
	Name      string `yaml:"name,omitempty"`
	MemoryMiB int    `yaml:"memory_mib,omitempty"`
}
type State struct {
	Job       *Job     `yaml:"job"`
	RequestID string   `yaml:"request_id"`
	Resources Resource `yaml:"resources"`
	RunnerID  string   `yaml:"runner_id"`
	Secrets   []string `yaml:"secret_names"`
}
type GitCredentials struct {
	Protocol   string  `json:"protocol"`
	OAuthToken *string `json:"oauth_token,omitempty"`
	PrivateKey *string `json:"private_key,omitempty"`
	Passphrase *string `json:"passphrase,omitempty"`
}
