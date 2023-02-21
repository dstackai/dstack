package gcp

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	secretmanager "cloud.google.com/go/secretmanager/apiv1"
	"cloud.google.com/go/secretmanager/apiv1/secretmanagerpb"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/models"
)

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

func (sm *GCPSecretManager) FetchSecret(ctx context.Context, repoData *models.RepoData, name string) (string, error) {
	key := getSecretKey(sm.bucket, repoData, name)
	return sm.getSecretValue(ctx, key)
}

func (sm *GCPSecretManager) FetchCredentials(ctx context.Context, repoData *models.RepoData) (*models.GitCredentials, error) {
	key := getCreadentialsKey(sm.bucket, repoData)
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
		return "", gerrors.Wrap(err)
	}
	return string(version.Payload.GetData()), nil
}

func getSecretKey(bucket string, repoData *models.RepoData, name string) string {
	repoPath := repoData.RepoDataPath("-")
	repoPath = strings.ReplaceAll(repoPath, ".", "-")
	return fmt.Sprintf("dstack-secrets-%s-%s-%s", bucket, repoPath, name)
}

func getCreadentialsKey(bucket string, repoData *models.RepoData) string {
	repoPath := repoData.RepoDataPath("-")
	repoPath = strings.ReplaceAll(repoPath, ".", "-")
	return fmt.Sprintf("dstack-credentials-%s-%s", bucket, repoPath)
}
