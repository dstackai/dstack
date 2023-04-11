package models

import (
	"fmt"
	"strings"
)

type Resource struct {
	CPUs          int    `yaml:"cpus,omitempty"`
	Memory        uint64 `yaml:"memory_mib,omitempty"`
	GPUs          []GPU  `yaml:"gpus,omitempty"`
	Interruptible bool   `yaml:"interruptible,omitempty"`
	ShmSize       int64  `yaml:"shm_size_mib,omitempty"`
	Local         bool   `json:"local"`
}

type Job struct {
	Apps         []App             `yaml:"apps"`
	Artifacts    []Artifact        `yaml:"artifacts"`
	Cache        []Cache           `yaml:"cache"`
	Commands     []string          `yaml:"commands"`
	Entrypoint   *[]string         `yaml:"entrypoint"`
	Environment  map[string]string `yaml:"env"`
	HostName     string            `yaml:"host_name"`
	Image        string            `yaml:"image_name"`
	JobID        string            `yaml:"job_id"`
	MasterJobID  string            `yaml:"master_job_id"`
	PortCount    int               `yaml:"port_count"`
	Ports        []string          `yaml:"ports"`
	Deps         []Dep             `yaml:"deps"`
	ProviderName string            `yaml:"provider_name"`

	RepoName           string `yaml:"repo_name"`
	RepoUsername       string `yaml:"repo_username"`
	GitHostName        string `yaml:"git_host_name"`
	GitPort            int    `yaml:"git_port,omitempty"`
	GitBranch          string `yaml:"git_branch"`
	RepoDiff           string `yaml:"repo_diff"`
	RepoDiffFilename   string `yaml:"repo_diff_filename,omitempty"`
	GitHash            string `yaml:"git_hash"`
	GitName            string `yaml:"git_name"`
	GitUserName        string `yaml:"git_user_name"`
	LocalRepoUserName  string `yaml:"local_repo_user_name,omitempty"`
	LocalRepoUserEmail string `yaml:"local_repo_user_email,omitempty"`

	RequestID    string       `yaml:"request_id"`
	Requirements Requirements `yaml:"requirements"`
	RunName      string       `yaml:"run_name"`
	RunnerID     string       `yaml:"runner_id"`
	Status       string       `yaml:"status"`
	SubmittedAt  uint64       `yaml:"submitted_at"`
	TagName      string       `yaml:"tag_name"`
	//Variables    map[string]interface{} `yaml:"variables"`
	WorkflowName string `yaml:"workflow_name"`
	WorkingDir   string `yaml:"working_dir"`

	RegistryAuth RegistryAuth `yaml:"registry_auth"`
}

type Dep struct {
	RepoName string `yaml:"repo_name,omitempty"`
	RunName  string `yaml:"run_name,omitempty"`
	Mount    bool   `yaml:"mount,omitempty"`
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

func (j *Job) RepoHostNameWithPort() string {
	if j.GitPort == 0 {
		return j.GitHostName
	}
	return fmt.Sprintf("%s:%d", j.GitHostName, j.GitPort)
}

func (j *Job) JobFilepath() string {
	return fmt.Sprintf("jobs/%s/%s.yaml", j.RepoName, j.JobID)
}

func (j *Job) JobHeadFilepathPrefix() string {
	return fmt.Sprintf("jobs/%s/l;%s;", j.RepoName, j.JobID)
}

func (j *Job) JobHeadFilepath() string {
	appsSlice := make([]string, len(j.Apps))
	for _, app := range j.Apps {
		appsSlice = append(appsSlice, app.Name)
	}
	artifactSlice := make([]string, len(j.Artifacts))
	for _, art := range j.Artifacts {
		artifactSlice = append(artifactSlice, art.Path)
	}
	return fmt.Sprintf(
		"jobs/%s/l;%s;%s;%s;%d;%s;%s;%s;%s",
		j.RepoName,
		j.JobID,
		j.ProviderName,
		j.RepoUsername,
		j.SubmittedAt,
		j.Status,
		strings.Join(artifactSlice, ","),
		strings.Join(appsSlice, ","),
		j.TagName,
	)
}

func (j *Job) JobHeadFilepathLocal() string {
	// TODO: we can get rid of this function once we stop putting artifact paths into job heads
	appsSlice := make([]string, len(j.Apps))
	for _, app := range j.Apps {
		appsSlice = append(appsSlice, app.Name)
	}
	artifactSlice := make([]string, len(j.Artifacts))
	for _, art := range j.Artifacts {
		artifactSlice = append(artifactSlice, strings.ReplaceAll(art.Path, "/", "_"))
	}
	return fmt.Sprintf(
		"jobs/%s/%s/%s/l;%s;%s;%s;%d;%s;%s;%s;%s",
		j.RepoName,
		j.JobID,
		j.ProviderName,
		j.LocalRepoUserName,
		j.SubmittedAt,
		j.Status,
		strings.Join(artifactSlice, ","),
		strings.Join(appsSlice, ","),
		j.TagName,
	)
}

func (j *Job) SecretsPrefix() string {
	return fmt.Sprintf("secrets/%s/l;", j.RepoName)
}
