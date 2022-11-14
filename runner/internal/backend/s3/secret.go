package local

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/secretsmanager"
	"github.com/aws/aws-sdk-go/aws"
	"github.com/dstackai/dstackai/runner/internal/gerrors"
	"github.com/dstackai/dstackai/runner/internal/log"
	"github.com/dstackai/dstackai/runner/internal/models"
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

func (sm *ClientSecret) fetchSecret(ctx context.Context, bucket string, secrets []string) (map[string]string, error) {
	result := make(map[string]string)
	for _, secret := range secrets {
		value, err := sm.cli.GetSecretValue(ctx, &secretsmanager.GetSecretValueInput{
			SecretId: aws.String(fmt.Sprintf("/dstack/%s/secrets/%s", bucket, secret)),
		})
		if err != nil {
			log.Error(ctx, "Fetching value secret S3", "bucket", bucket, "secret", secret, "err", err)
			return nil, gerrors.Wrap(err)
		}
		result[secret] = aws.StringValue(value.SecretString)
	}
	return result, nil
}

func (sm *ClientSecret) fetchCredentials(ctx context.Context, bucket, repoHostnameWithPort, repoUserName, repoName string) *models.GitCredentials {
	value, err := sm.cli.GetSecretValue(ctx, &secretsmanager.GetSecretValueInput{
		SecretId: aws.String(fmt.Sprintf("/dstack/%s/credentials/%s/%s/%s", bucket, repoHostnameWithPort, repoUserName, repoName)),
	})
	if err != nil {
		log.Error(ctx, "Fetching value credentials S3", "bucket", bucket, "RepoHostnameWithPort", repoHostnameWithPort, "RepoUserName", repoUserName, "RepoName", repoName, "err", err)
		return nil
	}
	cred := new(models.GitCredentials)
	err = json.Unmarshal([]byte(aws.StringValue(value.SecretString)), &cred)
	if err != nil {
		log.Error(ctx, "Unmarshal value credentials S3", "bucket", bucket, "RepoHostnameWithPort", repoHostnameWithPort, "RepoUserName", repoUserName, "RepoName", repoName, "err", err)
		return nil
	}
	return cred
}
