package azure

import (
	"context"
	"encoding/base32"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/Azure/azure-sdk-for-go/sdk/keyvault/azsecrets"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/models"
)

var ErrSecretNotFound = errors.New("secret not found")

type AzureSecretManager struct {
	secretClient *azsecrets.Client
}

func NewAzureSecretManager(credential *azidentity.DefaultAzureCredential, url string) (*AzureSecretManager, error) {
	secretClient, err := azsecrets.NewClient(url, credential, nil)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return &AzureSecretManager{
		secretClient: secretClient,
	}, nil
}

func (azsecret AzureSecretManager) FetchCredentials(ctx context.Context, repoId string) (*models.GitCredentials, error) {
	key, err := getCredentialKey(repoId)
	if err != nil {
		return nil, err
	}
	creds := models.GitCredentials{}
	data, err := azsecret.getSecretValue(ctx, key)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	if err = json.Unmarshal([]byte(data), &creds); err != nil {
		return nil, gerrors.Wrap(err)
	}
	return &creds, nil
}

func (azsecret AzureSecretManager) FetchSecret(ctx context.Context, repoId, name string) (string, error) {
	key, err := getSecretKey(repoId, name)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	return azsecret.getSecretValue(ctx, key)
}

func (azsecret AzureSecretManager) getSecretValue(ctx context.Context, key string) (string, error) {
	response, err := azsecret.secretClient.GetSecret(ctx, key, "", nil)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	return *response.Value, nil
}

func getSecretKey(repoId, name string) (string, error) {
	key_suffix := fmt.Sprintf("%s-%s", repoId, name)
	return encodeKey("dstack-secrets-", key_suffix), nil
}

func getCredentialKey(repoId string) (string, error) {
	key_suffix := repoId
	return encodeKey("dstack-credentials-", key_suffix), nil
}

func encodeKey(key_prefix, key_suffix string) string {
	data := []byte(key_suffix)
	dst := make([]byte, base32.StdEncoding.EncodedLen(len(data)))
	base32.StdEncoding.Encode(dst, data)
	key := fmt.Sprintf("%s%s", key_prefix, strings.ReplaceAll(string(dst), "=", "-"))
	return key
}
