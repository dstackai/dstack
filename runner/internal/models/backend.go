package models

import (
	"fmt"
	"strings"
	"time"
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
	// apply omitempty to every Optional[] in pydantic model
	AppNames          []string          `yaml:"app_names,omitempty"` // head
	Apps              []App             `yaml:"app_specs,omitempty"`
	ArtifactPaths     []string          `yaml:"artifact_paths,omitempty"` // head
	Artifacts         []Artifact        `yaml:"artifact_specs,omitempty"`
	BuildCommands     []string          `yaml:"build_commands,omitempty"`
	BuildPolicy       BuildPolicy       `yaml:"build_policy"`
	Cache             []Cache           `yaml:"cache_specs"`
	Commands          []string          `yaml:"commands,omitempty"`
	ConfigurationPath string            `yaml:"configuration_path,omitempty"` // head
	ConfigurationType ConfigurationType `yaml:"configuration_type,omitempty"`
	ContainerExitCode string            `yaml:"container_exit_code,omitempty"` // head
	CreatedAt         uint64            `yaml:"created_at"`
	Deps              []Dep             `yaml:"dep_specs,omitempty"`
	Entrypoint        []string          `yaml:"entrypoint,omitempty"`
	Environment       map[string]string `yaml:"env,omitempty"`
	ErrorCode         ErrorCode         `yaml:"error_code,omitempty"` // head
	Gateway           Gateway           `yaml:"gateway,omitempty"`
	HomeDir           string            `yaml:"home_dir,omitempty"`
	HostName          string            `yaml:"host_name,omitempty"`
	HubUserName       string            `yaml:"hub_user_name"` // head
	Image             string            `yaml:"image_name"`
	InstanceSpotType  string            `yaml:"instance_spot_type,omitempty"` // head
	InstanceType      string            `yaml:"instance_type,omitempty"`      // head
	JobID             string            `yaml:"job_id"`                       // head
	Location          string            `yaml:"location,omitempty"`
	MasterJobID       string            `yaml:"master_job,omitempty"`
	MaxDuration       uint64            `yaml:"max_duration,omitempty"`
	ProviderName      string            `yaml:"provider_name,omitempty"` // deprecated, head
	RegistryAuth      RegistryAuth      `yaml:"registry_auth,omitempty"`
	RepoCodeFilename  string            `yaml:"repo_code_filename,omitempty"`
	RepoData          RepoData          `yaml:"repo_data"`
	RepoRef           RepoRef           `yaml:"repo_ref"` // head
	RequestID         string            `yaml:"request_id,omitempty"`
	Requirements      Requirements      `yaml:"requirements,omitempty"`
	RetryPolicy       RetryPolicy       `yaml:"retry_policy,omitempty"`
	RunName           string            `yaml:"run_name"` // head
	RunnerID          string            `yaml:"runner_id,omitempty"`
	Setup             []string          `yaml:"setup"`
	SpotPolicy        SpotPolicy        `yaml:"spot_policy,omitempty"`
	Status            JobStatus         `yaml:"status"` // head
	SubmissionNum     int               `yaml:"submission_num"`
	SubmittedAt       uint64            `yaml:"submitted_at"`       // head
	TagName           string            `yaml:"tag_name,omitempty"` // head
	TerminationPolicy string            `yaml:"termination_policy,omitempty"`
	WorkflowName      string            `yaml:"workflow_name,omitempty"` // deprecated, head
	WorkingDir        string            `yaml:"working_dir,omitempty"`
}

type RepoRef struct {
	RepoId string `yaml:"repo_id"`
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

type RepoData struct {
	RepoType RepoType `yaml:"repo_type"`
	// type=remote
	RepoHostName    string `yaml:"repo_host_name,omitempty"`
	RepoPort        int    `yaml:"repo_port,omitempty"`
	RepoUserName    string `yaml:"repo_user_name,omitempty"`
	RepoName        string `yaml:"repo_name,omitempty"`
	RepoBranch      string `yaml:"repo_branch,omitempty"`
	RepoHash        string `yaml:"repo_hash,omitempty"`
	RepoConfigName  string `yaml:"repo_config_name,omitempty"`
	RepoConfigEmail string `yaml:"repo_config_email,omitempty"`
	// type=local
	RepoDir string `yaml:"repo_dir"`
}

type Gateway struct {
	Hostname    string `yaml:"hostname"`
	SSHKey      string `yaml:"ssh_key,omitempty"`
	ServicePort int    `yaml:"service_port"`
	PublicPort  int    `yaml:"public_port"`
}

type RunnerMetadata struct {
	Status string `yaml:"status"`
}

type ConfigurationType string
type ErrorCode string
type SpotPolicy string
type TerminationPolicy string
type JobStatus string
type BuildPolicy string
type RepoType string

const (
	UseBuild   BuildPolicy = "use-build"
	Build      BuildPolicy = "build"
	ForceBuild BuildPolicy = "force-build"
	BuildOnly  BuildPolicy = "build-only"
)

func (j *Job) RepoHostNameWithPort() string {
	if j.RepoData.RepoPort == 0 {
		return j.RepoData.RepoHostName
	}
	return fmt.Sprintf("%s:%d", j.RepoData.RepoHostName, j.RepoData.RepoPort)
}

func (j *Job) JobFilepath() string {
	return fmt.Sprintf("jobs/%s/%s.yaml", j.RepoRef.RepoId, j.JobID)
}

func (j *Job) JobHeadFilepathPrefix() string {
	return fmt.Sprintf("jobs/%s/l;%s;", j.RepoRef.RepoId, j.JobID)
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
		j.RepoRef.RepoId,
		j.JobID,
		"", // ProviderName
		j.HubUserName,
		j.SubmittedAt,
		strings.Join([]string{string(j.Status), string(j.ErrorCode), j.ContainerExitCode}, ","),
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
	return fmt.Sprintf("secrets/%s/l;", j.RepoRef.RepoId)
}

func (j *Job) MaxDurationExceeded() bool {
	if j.MaxDuration == 0 {
		return false
	}
	now := uint64(time.Now().Unix())
	return now > j.SubmittedAt/1000+j.MaxDuration
}
