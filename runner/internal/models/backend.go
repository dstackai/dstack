package models

import (
	"fmt"
	"strings"
)

type Resource struct {
	CPUs    int    `yaml:"cpus,omitempty"`
	Memory  uint64 `yaml:"memory_mib,omitempty"`
	GPUs    []GPU  `yaml:"gpus,omitempty"`
	Spot    bool   `yaml:"spot,omitempty"`
	ShmSize int64  `yaml:"shm_size_mib,omitempty"`
	Local   bool   `json:"local"`
}

type Job struct {
	Apps                  []App             `yaml:"apps"`
	Artifacts             []Artifact        `yaml:"artifacts"`
	Cache                 []Cache           `yaml:"cache"`
	BuildCommands         []string          `yaml:"build_commands"`
	OptionalBuildCommands []string          `yaml:"optional_build_commands"`
	Commands              []string          `yaml:"commands"`
	BuildPolicy           BuildPolicy       `yaml:"build_policy"`
	Entrypoint            []string          `yaml:"entrypoint"`
	Environment           map[string]string `yaml:"env"`
	RunEnvironment        map[string]string `yaml:"run_env"`
	HostName              string            `yaml:"host_name"`
	Image                 string            `yaml:"image_name"`
	JobID                 string            `yaml:"job_id"`
	MasterJobID           string            `yaml:"master_job_id"`
	Deps                  []Dep             `yaml:"deps"`
	ProviderName          string            `yaml:"provider_name"`

	RepoId      string `yaml:"repo_id"`
	RepoType    string `yaml:"repo_type"`
	HubUserName string `yaml:"hub_user_name"`

	RepoHostName    string `yaml:"repo_host_name,omitempty"`
	RepoPort        int    `yaml:"repo_port,omitempty"`
	RepoUserName    string `yaml:"repo_user_name,omitempty"`
	RepoName        string `yaml:"repo_name,omitempty"`
	RepoBranch      string `yaml:"repo_branch,omitempty"`
	RepoHash        string `yaml:"repo_hash,omitempty"`
	RepoConfigName  string `yaml:"repo_config_name,omitempty"`
	RepoConfigEmail string `yaml:"repo_config_email,omitempty"`

	RepoCodeFilename string `yaml:"repo_code_filename"`

	RequestID         string       `yaml:"request_id"`
	Location          string       `yaml:"location"`
	Requirements      Requirements `yaml:"requirements"`
	RunName           string       `yaml:"run_name"`
	RunnerID          string       `yaml:"runner_id"`
	SpotPolicy        string       `yaml:"spot_policy"`
	RetryPolicy       RetryPolicy  `yaml:"retry_policy"`
	Status            string       `yaml:"status"`
	ErrorCode         string       `yaml:"error_code,omitempty"`
	ContainerExitCode string       `yaml:"container_exit_code,omitempty"`
	CreatedAt         uint64       `yaml:"created_at"`
	SubmittedAt       uint64       `yaml:"submitted_at"`
	SubmissionNum     int          `yaml:"submission_num"`
	TagName           string       `yaml:"tag_name"`
	InstanceType      string       `yaml:"instance_type"`
	ConfigurationPath string       `yaml:"configuration_path"`
	ConfigurationType string       `yaml:"configuration_type"`
	WorkflowName      string       `yaml:"workflow_name"` // deprecated
	HomeDir           string       `yaml:"home_dir"`
	WorkingDir        string       `yaml:"working_dir"`

	RegistryAuth RegistryAuth `yaml:"registry_auth"`
}

type Dep struct {
	RepoId      string `yaml:"repo_id,omitempty"`
	HubUserName string `yaml:"hub_user_name,omitempty"`
	RunName     string `yaml:"run_name,omitempty"`
	Mount       bool   `yaml:"mount,omitempty"`
}

type Artifact struct {
	Path  string `yaml:"path,omitempty"`
	Mount bool   `yaml:"mount,omitempty"`
}

type Cache struct {
	Path string `yaml:"path"`
}

type App struct {
	Name           string            `yaml:"app_name"`
	Port           int               `yaml:"port"`
	MapToPort      int               `yaml:"map_to_port"`
	UrlPath        string            `yaml:"url_path"`
	UrlQueryParams map[string]string `yaml:"url_query_params"`
}

type Requirements struct {
	GPUs    GPU   `yaml:"gpus,omitempty"`
	CPUs    int   `yaml:"cpus,omitempty"`
	Memory  int   `yaml:"memory_mib,omitempty"`
	Spot    bool  `yaml:"spot,omitempty"`
	ShmSize int64 `yaml:"shm_size_mib,omitempty"`
	Local   bool  `json:"local"`
}

type GPU struct {
	Count     int    `yaml:"count,omitempty"`
	Name      string `yaml:"name,omitempty"`
	MemoryMiB int    `yaml:"memory_mib,omitempty"`
}

type RetryPolicy struct {
	Retry bool `yaml:"retry"`
	Limit int  `yaml:"limit,omitempty"`
}

type State struct {
	Job       *Job     `yaml:"job"`
	RequestID string   `yaml:"request_id"`
	Resources Resource `yaml:"resources"`
	RunnerID  string   `yaml:"runner_id"`
}

type GitCredentials struct {
	Protocol   string  `json:"protocol"`
	OAuthToken *string `json:"oauth_token,omitempty"`
	PrivateKey *string `json:"private_key,omitempty"`
	Passphrase *string `json:"passphrase,omitempty"`
}

type RegistryAuth struct {
	Username string `yaml:"username,omitempty"`
	Password string `yaml:"password,omitempty"`
}

type RunnerMetadata struct {
	Status string `yaml:"status"`
}

type BuildPolicy string

const (
	UseBuild   BuildPolicy = "use-build"
	Build      BuildPolicy = "build"
	ForceBuild BuildPolicy = "force-build"
	BuildOnly  BuildPolicy = "build-only"
)

func (j *Job) RepoHostNameWithPort() string {
	if j.RepoPort == 0 {
		return j.RepoHostName
	}
	return fmt.Sprintf("%s:%d", j.RepoHostName, j.RepoPort)
}

func (j *Job) JobFilepath() string {
	return fmt.Sprintf("jobs/%s/%s.yaml", j.RepoId, j.JobID)
}

func (j *Job) JobHeadFilepathPrefix() string {
	return fmt.Sprintf("jobs/%s/l;%s;", j.RepoId, j.JobID)
}

func (j *Job) JobHeadFilepath() string {
	appsSlice := make([]string, len(j.Apps))
	for i, app := range j.Apps {
		appsSlice[i] = app.Name
	}
	artifactSlice := make([]string, len(j.Artifacts))
	for i, art := range j.Artifacts {
		artifactSlice[i] = EscapeHead(art.Path)
	}
	return fmt.Sprintf(
		"jobs/%s/l;%s;%s;%s;%d;%s;%s;%s;%s;%s;%s;%s",
		j.RepoId,
		j.JobID,
		j.ProviderName,
		j.HubUserName,
		j.SubmittedAt,
		strings.Join([]string{j.Status, j.ErrorCode, j.ContainerExitCode}, ","),
		strings.Join(artifactSlice, ","),
		strings.Join(appsSlice, ","),
		j.TagName,
		j.InstanceType,
		EscapeHead(j.ConfigurationPath),
		j.GetInstanceType(),
	)
}

func (j *Job) GetInstanceType() string {
	if j.Requirements.Spot {
		return "spot"
	}
	return "on-demand"
}

func (j *Job) SecretsPrefix() string {
	return fmt.Sprintf("secrets/%s/l;", j.RepoId)
}
