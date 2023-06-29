package lambda

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"

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
