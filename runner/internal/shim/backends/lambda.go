package backends

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"os"

	"github.com/dstackai/dstack/runner/internal/gerrors"
)

const LAMBDA_API_URL = "https://cloud.lambdalabs.com/api/v1"

type LambdaAPIClient struct {
	apiKey string
}

type TerminateInstanceRequest struct {
	InstanceIDs []string `json:"instance_ids"`
}

func NewLambdaAPIClient(apiKey string) *LambdaAPIClient {
	return &LambdaAPIClient{apiKey: apiKey}
}

func (client *LambdaAPIClient) TerminateInstance(ctx context.Context, instanceIDs []string) error {
	body, err := json.Marshal(TerminateInstanceRequest{InstanceIDs: instanceIDs})
	if err != nil {
		return gerrors.Wrap(err)
	}
	req, err := http.NewRequest("POST", LAMBDA_API_URL+"/instance-operations/terminate", bytes.NewReader(body))
	if err != nil {
		return gerrors.Wrap(err)
	}
	req.Header.Add("Authorization", "Bearer "+client.apiKey)
	httpClient := http.Client{}
	resp, err := httpClient.Do(req)
	if err != nil {
		return gerrors.Wrap(err)
	}
	if resp.StatusCode == 200 {
		return nil
	}
	return gerrors.Newf("/instance-operations/terminate returned non-200 status code: %s", resp.Status)
}

const LAMBDA_CONFIG_PATH = "/home/ubuntu/.dstack/config.json"

type LambdaConfig struct {
	InstanceID string `json:"instance_id"`
	ApiKey     string `json:"api_key"`
}

type LambdaBackend struct {
	apiClient *LambdaAPIClient
	config    LambdaConfig
}

func init() {
	register("lambda", NewLambdaBackend)
}

func NewLambdaBackend(ctx context.Context) (Backend, error) {
	config := LambdaConfig{}
	fileContent, err := os.ReadFile(LAMBDA_CONFIG_PATH)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	err = json.Unmarshal(fileContent, &config)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return &LambdaBackend{
		apiClient: NewLambdaAPIClient(config.ApiKey),
		config:    config,
	}, nil
}

func (b *LambdaBackend) Terminate(ctx context.Context) error {
	return gerrors.Wrap(b.apiClient.TerminateInstance(ctx, []string{b.config.InstanceID}))
}
