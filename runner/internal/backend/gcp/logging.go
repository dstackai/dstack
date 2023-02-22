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

type GCPLogger struct {
	client *logging.Client
	logger *logging.Logger
	jobID  string
}

func NewGCPLogger(ctx context.Context, project, jobID, logGroup, logName string) *GCPLogger {
	client, err := logging.NewClient(ctx, project)
	if err != nil {
		return nil
	}
	logID := getLogID(logGroup, logName)
	logger := client.Logger(logID)
	return &GCPLogger{
		client: client,
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
			glogger.client.Close()
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
