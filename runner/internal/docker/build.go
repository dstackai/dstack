package docker

import (
	"bytes"
	"crypto/sha256"
	"fmt"
)

type BuildSpec struct {
	BaseImageID       string
	WorkDir           string
	ConfigurationPath string
	ConfigurationType string

	Commands           []string
	Entrypoint         []string
	Env                []string
	BaseImageName      string
	RegistryAuthBase64 string
	RepoPath           string
	Platform           string
	RepoId             string

	ShmSize int64
}

func (s *BuildSpec) Hash() string {
	var buffer bytes.Buffer
	buffer.WriteString(s.BaseImageID)
	buffer.WriteString("\n")
	buffer.WriteString(s.WorkDir)
	buffer.WriteString("\n")
	buffer.WriteString(s.ConfigurationPath)
	buffer.WriteString("\n")
	buffer.WriteString(s.ConfigurationType)
	buffer.WriteString("\n")
	return fmt.Sprintf("%x", sha256.Sum256(buffer.Bytes()))
}
