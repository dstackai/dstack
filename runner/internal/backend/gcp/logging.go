package gcp

import (
	"context"
	"fmt"
	"strings"
	"time"

	"cloud.google.com/go/logging"
)

const FLUSH_INTERVAL = 250 * time.Millisecond

type LogMesage struct {
	JobID  string `json:"job_id"`
	Log    string `json:"log"`
	Source string `json:"source"`
}

type GCPLogging struct {
	client *logging.Client
}

type GCPLogger struct {
	logger *logging.Logger
	jobID  string
}

func NewGCPLogging(project string) *GCPLogging {
	ctx := context.TODO()
	client, err := logging.NewClient(ctx, project)
	if err != nil {
		return nil
	}
	return &GCPLogging{client: client}
}

func (glogging *GCPLogging) NewGCPLogger(ctx context.Context, jobID, logGroup, logName string) *GCPLogger {
	logID := getLogID(logGroup, logName)
	logger := glogging.client.Logger(logID)
	return &GCPLogger{
		jobID:  jobID,
		logger: logger,
	}
}

func (glogger *GCPLogger) Launch(ctx context.Context) {
	ticker := time.NewTicker(FLUSH_INTERVAL)
	go glogger.flushLogs(ctx, ticker)
}

func (glogger *GCPLogger) Write(b []byte) (int, error) {
	msg := LogMesage{
		JobID:  glogger.jobID,
		Log:    string(b),
		Source: "stdout",
	}
	entry := logging.Entry{Payload: msg}
	glogger.logger.Log(entry)
	return len(b), nil
}

func (glogger *GCPLogger) flushLogs(ctx context.Context, ticker *time.Ticker) {
	for {
		select {
		case <-ctx.Done():
			// Backend will Close() the client on Shutdown(), flushing the logs.
			// We don't want to Close() from this goroutine since google libraries may
			// send audit logs after ctx.Done().
			glogger.logger.Flush()
			return
		case <-ticker.C:
			glogger.logger.Flush()
		}
	}
}

func getLogID(logGroup, logName string) string {
	logGroup = strings.ReplaceAll(logGroup, "/", "-")
	logGroup = strings.TrimLeft(logGroup, "-")
	return fmt.Sprintf("%s-%s", logGroup, logName)
}
