package gcp

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	secretmanager "cloud.google.com/go/secretmanager/apiv1"
	"cloud.google.com/go/secretmanager/apiv1/secretmanagerpb"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/models"
)

var ErrSecretNotFound = errors.New("secret not found")

type GCPSecretManager struct {
	client  *secretmanager.Client
	project string
	bucket  string
}

func NewGCPSecretManager(project, bucket string) *GCPSecretManager {
	ctx := context.TODO()
	client, err := secretmanager.NewClient(ctx)
	if err != nil {
		return nil
	}
	return &GCPSecretManager{
		client:  client,
		project: project,
		bucket:  bucket,
	}
}

func (sm *GCPSecretManager) FetchSecret(ctx context.Context, repoId string, name string) (string, error) {
	key := getSecretKey(sm.bucket, repoId, name)
	return sm.getSecretValue(ctx, key)
}

func (sm *GCPSecretManager) FetchCredentials(ctx context.Context, repoId string) (*models.GitCredentials, error) {
	key := getCredentialsKey(sm.bucket, repoId)
	creds := new(models.GitCredentials)
	data, err := sm.getSecretValue(ctx, key)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	json.Unmarshal([]byte(data), creds)
	return creds, nil
}

func (sm *GCPSecretManager) getSecretValue(ctx context.Context, key string) (string, error) {
	resource := fmt.Sprintf("projects/%s/secrets/%s/versions/latest", sm.project, key)
	req := &secretmanagerpb.AccessSecretVersionRequest{
		Name: resource,
	}
	version, err := sm.client.AccessSecretVersion(ctx, req)
	if err != nil {
		if strings.Contains(err.Error(), "NotFound") {
			return "", gerrors.Wrap(ErrSecretNotFound)
		} else {
			return "", gerrors.Wrap(err)
		}
	}
	return string(version.Payload.GetData()), nil
}

func getSecretKey(bucket string, repoId string, name string) string {
	repoId = strings.ReplaceAll(repoId, ".", "-")
	return fmt.Sprintf("dstack-secrets-%s-%s-%s", bucket, repoId, name)
}

func getCredentialsKey(bucket string, repoId string) string {
	repoId = strings.ReplaceAll(repoId, ".", "-")
	return fmt.Sprintf("dstack-credentials-%s-%s", bucket, repoId)
}
