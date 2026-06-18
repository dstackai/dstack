package backends

import (
	"fmt"
)

func GetBackend(backendType string) (Backend, error) {
	switch backendType {
	case "aws":
		return NewAWSBackend(), nil
	case "gcp":
		return NewGCPBackend(), nil
	}
	return nil, fmt.Errorf("unknown backend: %q", backendType)
}
