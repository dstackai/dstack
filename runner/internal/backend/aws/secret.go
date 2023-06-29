package aws

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/secretsmanager"
	"github.com/aws/aws-sdk-go/aws"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/models"
)

type ClientSecret struct {
	cli *secretsmanager.Client
}

func NewClientSecret(region string) *ClientSecret {
	c := new(ClientSecret)
	ctx := context.TODO()
	cfg, err := config.LoadDefaultConfig(
		ctx,
		config.WithRegion(region),
	)
	if err != nil {
		return nil
	}
	c.cli = secretsmanager.NewFromConfig(cfg)
	return c
}

func (sm *ClientSecret) fetchSecret(ctx context.Context, bucket string, secrets map[string]string) (map[string]string, error) {
	result := make(map[string]string)
	for secret, secretPath := range secrets {
		value, err := sm.cli.GetSecretValue(ctx, &secretsmanager.GetSecretValueInput{
			SecretId: aws.String(fmt.Sprintf("/dstack/%s/secrets/%s", bucket, secretPath)),
		})
		if err != nil {
			log.Error(ctx, "Fetching value secret S3", "bucket", bucket, "secret", secret, "secret_path", secretPath, "err", err)
			return nil, gerrors.Wrap(err)
		}
		result[secret] = aws.StringValue(value.SecretString)
	}
	return result, nil
}

func (sm *ClientSecret) fetchCredentials(ctx context.Context, bucket, repoId string) *models.GitCredentials {
	value, err := sm.cli.GetSecretValue(ctx, &secretsmanager.GetSecretValueInput{
		SecretId: aws.String(fmt.Sprintf("/dstack/%s/credentials/%s", bucket, repoId)),
	})
	if err != nil {
		log.Error(ctx, "Fetching value credentials S3", "bucket", bucket, "RepoId", repoId, "err", err)
		return nil
	}
	cred := new(models.GitCredentials)
	err = json.Unmarshal([]byte(aws.StringValue(value.SecretString)), &cred)
	if err != nil {
		log.Error(ctx, "Unmarshal value credentials S3", "bucket", bucket, "RepoId", repoId, "err", err)
		return nil
	}
	return cred
}
