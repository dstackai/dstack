package common

import (
	"context"
	"os"
	"path/filepath"

	"github.com/sirupsen/logrus"
	"gitlab.com/dstackai/dstackai-runner/consts"
	"gitlab.com/dstackai/dstackai-runner/internal/log"
)

func HomeDir() string {
	home, err := os.UserHomeDir()
	if err != nil {
		log.Error(context.Background(), "Failed to find homedir", "err", err)
	}
	return home
}

func CreateTMPDir() {
	theTempPath := filepath.Join(HomeDir(), consts.TMP_DIR_PATH)
	if _, err := os.Stat(theTempPath); os.IsNotExist(err) {
		err = os.MkdirAll(theTempPath, 0777)
		if err != nil {
			logrus.Errorf("Failed to create .dstack/tmp directory, make sure that you have rights")
			os.Exit(1)
		}
	}
	theArtifactsPath := filepath.Join(HomeDir(), consts.USER_ARTIFACTS_PATH)
	if _, err := os.Stat(theArtifactsPath); os.IsNotExist(err) {
		err = os.MkdirAll(theArtifactsPath, 0777)
		if err != nil {
			logrus.Errorf("Failed to create .dstack/tmp directory, make sure that you have rights")
			os.Exit(1)
		}
	}
}
