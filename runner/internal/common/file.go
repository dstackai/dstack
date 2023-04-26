package common

import (
	"context"
	"os"

	"github.com/dstackai/dstack/runner/internal/log"
)

func HomeDir() string {
	home, err := os.UserHomeDir()
	if err != nil {
		log.Error(context.Background(), "Failed to find homedir", "err", err)
	}
	return home
}
