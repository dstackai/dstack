package models

import (
	"github.com/dstackai/dstackai/runner/internal/states"
)

type Run struct {
	RunName      string            `json:"run_name"`
	WorkflowName string            `json:"workflow_name"`
	UserName     string            `json:"user_name"`
	RepoURL      string            `json:"repo_url"`
	RepoBranch   string            `json:"repo_branch"`
	RepoHash     string            `json:"repo_hash"`
	RepoDiff     string            `json:"repo_diff"`
	Config       map[string]string `json:"variables"`
	SubmittedAt  int64             `json:"submitted_at"`
	Status       states.State      `json:"status"`
	RunnerID     string            `json:"runner_id"`
	UpdatedAt    int64             `json:"updated_at"`
}

type JobReference struct {
	JobId    string `json:"job_id"`
	RunName  string `json:"run_name"`
	UserName string `json:"user_name"`
}

type Configuration struct {
	AccessKeyId       string `json:"aws_access_key_id"`
	SecretAccessKey   string `json:"aws_secret_access_key"`
	Region            string `json:"aws_region"`
	ArtifactsS3Bucket string `json:"artifacts_s3_bucket"`
}

type Workflow struct {
	Steps []Step `yaml:"workflows"`
}

// Job
type Step struct {
	Name      string    `yaml:"name"`
	Params    []Params  `yaml:"variables"`
	DependsOn DependsOn `yaml:"depends-on,omitempty"`
}

type Resources struct {
	Cpu struct {
		Count int `yaml:"count" json:"count"`
	} `yaml:"cpu,omitempty" json:"cpu,omitempty"`
	Memory string `yaml:"memory,omitempty" json:"memory,omitempty"`
	Gpu    struct {
		Name   string `yaml:"name" json:"name"`
		Count  int    `yaml:"count" json:"count"`
		Memory string `yaml:"memory" json:"memory"`
	} `yaml:"gpu,omitempty" json:"gpu,omitempty"`
}

// Variables
type Params struct {
	Name    string `yaml:"name"`
	Default string `yaml:"default"`
}

// DependsOn
type DependsOn struct {
	Workflows []string `yaml:"workflows"`
	Repo      Repo     `yaml:"repo"`
}

// Repo
type Repo struct {
	Include []string `yaml:"include"`
}

// Variables
type Variables struct {
	Configs map[string]map[string]string `yaml:"variables"`
}

// Runner.yaml
type Resource struct {
	Interruptible bool   `yaml:"interruptible"`
	Cpus          int    `yaml:"cpus" json:"cpus"`
	MemoryMiB     uint64 `yaml:"memory_mib" json:"memory_mib"`
	Gpus          []Gpu  `yaml:"gpus" json:"gpus"`
}

type Gpu struct {
	Name      string `yaml:"name" json:"name"`
	MemoryMiB uint64 `yaml:"memory_mib" json:"memory_mib"`
}

type MasterJob struct {
	JobID    string
	Hostname string
	Ports    []string
}
