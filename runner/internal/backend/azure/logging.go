package azure

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/Azure/azure-sdk-for-go/sdk/azcore"
	"github.com/Azure/azure-sdk-for-go/sdk/azcore/policy"
	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/Azure/azure-sdk-for-go/sdk/resourcemanager/monitor/armmonitor"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
)

const DSTACK_LOGS_TABLE = "dstack_logs_CL"
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

func NewAzureLoggingClient(ctx context.Context, credential *azidentity.DefaultAzureCredential, subscriptionId, resourceGroup, storageAccount string) *AzureLoggingClient {
	log.Trace(ctx, "Initializing AzureLoggingClient")
	dceName := getDataCollectionEndpointName(storageAccount)
	dceUrl, err := getDataCollectionEndpointUrl(ctx, credential, subscriptionId, resourceGroup, dceName)
	if err != nil {
		log.Error(ctx, "Failed to get DCE url", "err", err)
		return nil
	}
	dcrName := getDataCollectionRuleName(storageAccount)
	dcrId, err := getDataCollectionRuleId(ctx, credential, subscriptionId, resourceGroup, dcrName)
	if err != nil {
		log.Error(ctx, "Failed to get DCR id", "err", err)
		return nil
	}
	return &AzureLoggingClient{
		dceUrl:     dceUrl,
		dcrId:      dcrId,
		streamName: getDstackCustomLogsStreamName(),
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

func getDstackCustomLogsStreamName() string {
	return "Custom-" + DSTACK_LOGS_TABLE
}

func getDataCollectionEndpointName(storageAccount string) string {
	return fmt.Sprintf("%s-dce", storageAccount)
}

func getDataCollectionEndpointUrl(ctx context.Context, credential *azidentity.DefaultAzureCredential, subscriptionId, resourceGroup, dceName string) (string, error) {
	client, err := armmonitor.NewDataCollectionEndpointsClient(
		subscriptionId,
		credential,
		nil,
	)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	dce, err := client.Get(ctx, resourceGroup, dceName, nil)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	return *dce.DataCollectionEndpointResource.Properties.LogsIngestion.Endpoint, nil
}

func getDataCollectionRuleName(storageAccount string) string {
	return fmt.Sprintf("%s-dcr", storageAccount)
}

func getDataCollectionRuleId(ctx context.Context, credential *azidentity.DefaultAzureCredential, subscriptionId, resourceGroup, dcrName string) (string, error) {
	client, err := armmonitor.NewDataCollectionRulesClient(
		subscriptionId,
		credential,
		nil,
	)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	dcr, err := client.Get(ctx, resourceGroup, dcrName, nil)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	return *dcr.DataCollectionRuleResource.Properties.ImmutableID, nil
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
	resp, err := client.Do(req)
	if err != nil {
		return gerrors.Wrap(err)
	}
	if resp.StatusCode != 200 {
		body, _ := io.ReadAll(resp.Body)
		return gerrors.New(string(body))
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
