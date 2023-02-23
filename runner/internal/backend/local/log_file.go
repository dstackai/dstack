package local

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/dstackai/dstack/runner/consts"
	"github.com/dstackai/dstack/runner/internal/common"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/sirupsen/logrus"
)

type Logger struct {
	logger *logrus.Entry
}

func (l *Logger) Write(p []byte) (int, error) {
	return l.logger.Writer().Write(p)
}

func NewLogger(logGroup, logName string) (*Logger, error) {
	//std := logrus.StandardLogger()
	if _, err := os.Stat(filepath.Join(common.HomeDir(), consts.DSTACK_DIR_PATH, "logs", logGroup)); err != nil {
		if err = os.MkdirAll(filepath.Join(common.HomeDir(), consts.DSTACK_DIR_PATH, "logs", logGroup), 0777); err != nil {
			return nil, gerrors.Wrap(err)
		}
	}
	f, err := os.OpenFile(filepath.Join(common.HomeDir(), consts.DSTACK_DIR_PATH, "logs", logGroup, fmt.Sprintf("%s.log", logName)), os.O_WRONLY|os.O_CREATE|os.O_APPEND, 0777)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	logger := logrus.New()
	logger.SetOutput(f)
	l := Logger{logger: logrus.NewEntry(logger)}
	return &l, nil
}
