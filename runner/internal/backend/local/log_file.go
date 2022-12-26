package local

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/dstackai/dstackai/runner/consts"
	"github.com/dstackai/dstackai/runner/internal/common"
	"github.com/dstackai/dstackai/runner/internal/gerrors"
	"github.com/sirupsen/logrus"
)

type Logger struct {
	logger *logrus.Entry
}

func NewLogger(logGroup, logName string) (*Logger, error) {
	std := logrus.StandardLogger()
	f, err := os.OpenFile(filepath.Join(common.HomeDir(), consts.DSTACK_DIR_PATH, "logs", logGroup, fmt.Sprintf("%s.log", logName)), os.O_WRONLY|os.O_CREATE|os.O_APPEND, 0777)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	std.SetOutput(f)
	l := Logger{logger: logrus.NewEntry(std)}
	return &l, nil
}
