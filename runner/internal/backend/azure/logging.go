package azure

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/Azure/azure-sdk-for-go/sdk/azcore"
	"github.com/Azure/azure-sdk-for-go/sdk/azcore/policy"
	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/dstackai/dstack/runner/internal/gerrors"
)

const FLUSH_INTERVAL = 1000 * time.Millisecond

type JsonPayload struct {
	JobID  string `json:"job_id"`
	Log    string `json:"log"`
	Source string `json:"source"`
}

type LogEntry struct {
	LogName       string      `json:"LogName"`
	JsonPayload   JsonPayload `json:"JsonPayload"`
	TimeGenerated string      `json:"TimeGenerated"`
}

type AzureLoggingClient struct {
	dceUrl     string
	dcrId      string
	streamName string
	credential *azidentity.DefaultAzureCredential
	token      azcore.AccessToken
}

type AzureLogger struct {
	client  *AzureLoggingClient
	jobID   string
	logName string
	logBuff []LogEntry
	logCh   chan LogEntry
}

func NewAzureLoggingClient(credential *azidentity.DefaultAzureCredential, dceUrl, dcrId, streamName string) *AzureLoggingClient {
	return &AzureLoggingClient{
		dceUrl:     dceUrl,
		dcrId:      dcrId,
		streamName: streamName,
		credential: credential,
	}
}

func NewAzureLogger(client *AzureLoggingClient, jobID, logGroup, logStream string) *AzureLogger {
	logName := getLogName(logGroup, logStream)
	return &AzureLogger{
		client:  client,
		jobID:   jobID,
		logName: logName,
		logCh:   make(chan LogEntry, 100),
	}
}

func (azlogger *AzureLogger) Launch(ctx context.Context) error {
	token, err := azlogger.client.credential.GetToken(
		ctx, policy.TokenRequestOptions{Scopes: []string{"https://monitor.azure.com"}},
	)
	if err != nil {
		return gerrors.Wrap(err)
	}
	// TODO refresh token
	azlogger.client.token = token
	ticker := time.NewTicker(FLUSH_INTERVAL)
	go azlogger.flushLogs(ctx, ticker)
	return nil
}

func (azlogger *AzureLogger) Write(p []byte) (int, error) {
	logEntry := azlogger.makeLogEntry(p)
	azlogger.logCh <- logEntry
	return len(p), nil
}

func getLogName(logGroup, logStream string) string {
	logGroup = strings.ReplaceAll(logGroup, "/", "-")
	logGroup = strings.TrimLeft(logGroup, "-")
	return fmt.Sprintf("%s-%s", logGroup, logStream)
}

func (azlogger *AzureLogger) makeLogEntry(data []byte) LogEntry {
	return LogEntry{
		LogName:       azlogger.logName,
		TimeGenerated: time.Now().UTC().Format("2006-01-02T15:04:05.000000Z"),
		JsonPayload: JsonPayload{
			JobID:  azlogger.jobID,
			Log:    string(data),
			Source: "stdout",
		},
	}
}

func (azlogger *AzureLogger) flushLogs(ctx context.Context, ticker *time.Ticker) {
	for {
		select {
		case <-ctx.Done():
			azlogger.doFlush()
			return
		case <-ticker.C:
			azlogger.doFlush()
		case logEntry := <-azlogger.logCh:
			azlogger.logBuff = append(azlogger.logBuff, logEntry)
		}
	}
}

func (azlogger *AzureLogger) doFlush() {
	if len(azlogger.logBuff) == 0 {
		return
	}
	azlogger.writeLogs(azlogger.logBuff)
	azlogger.logBuff = azlogger.logBuff[:0]
}

func (azlogger *AzureLogger) writeLogs(logs []LogEntry) error {
	logsUrl := azlogger.getLogsUrl()
	data, err := json.Marshal(logs)
	if err != nil {
		return gerrors.Wrap(err)
	}
	req, err := http.NewRequest("POST", logsUrl, bytes.NewReader(data))
	if err != nil {
		return gerrors.Wrap(err)
	}
	req.Header.Add("Authorization", "Bearer "+azlogger.client.token.Token)
	req.Header.Add("Content-type", "application/json")
	client := http.Client{}
	_, err = client.Do(req)
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (azlogger *AzureLogger) getLogsUrl() string {
	return fmt.Sprintf(
		"%s/dataCollectionRules/%s/streams/%s?api-version=2023-01-01",
		azlogger.client.dceUrl,
		azlogger.client.dcrId,
		azlogger.client.streamName,
	)
}
