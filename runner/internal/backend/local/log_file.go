package local

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"

	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/sirupsen/logrus"
)

type Logger struct {
	jobID       string
	logger      *logrus.Entry
	writer      *io.PipeWriter
	logsWritten int
}

type LogMesage struct {
	JobID   string `json:"job_id"`
	EventID int    `json:"event_id"`
	Log     string `json:"log"`
	Source  string `json:"source"`
}

func NewLogger(jobID, path, logGroup, logName string) (*Logger, error) {
	if _, err := os.Stat(filepath.Join(path, "logs", logGroup)); err != nil {
		if err = os.MkdirAll(filepath.Join(path, "logs", logGroup), 0777); err != nil {
			return nil, gerrors.Wrap(err)
		}
	}
	f, err := os.OpenFile(filepath.Join(path, "logs", logGroup, fmt.Sprintf("%s.log", logName)), os.O_WRONLY|os.O_CREATE|os.O_APPEND, 0777)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	logger := logrus.New()
	logger.SetFormatter(&logrus.TextFormatter{
		FullTimestamp:   true,
		TimestampFormat: "2006-01-02T15:04:05.999999Z07:00",
	})
	logger.SetOutput(f)
	logEntry := logrus.NewEntry(logger)
	logWriter := logEntry.Writer()
	l := Logger{jobID: jobID, logger: logEntry, writer: logWriter}
	return &l, nil
}

func (l *Logger) Write(p []byte) (int, error) {
	msg := LogMesage{
		JobID:   l.jobID,
		EventID: l.logsWritten,
		Log:     string(p),
		Source:  "stdout",
	}
	msgBytes, err := json.Marshal(msg)
	if err != nil {
		return 0, gerrors.Wrap(err)
	}
	msgBytes = append(msgBytes, '\n')
	_, err = l.writer.Write(msgBytes)
	if err != nil {
		return 0, gerrors.Wrap(err)
	}
	l.logsWritten += 1
	return len(p), nil
}
