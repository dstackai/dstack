package azure

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/Azure/azure-sdk-for-go/sdk/keyvault/azsecrets"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/models"
	"gitlab.com/golang-commonmark/puny"
	"regexp"
	"strings"
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

func (azsecret AzureSecretManager) FetchCredentials(ctx context.Context, repoData *models.RepoData) (*models.GitCredentials, error) {
	key, err := getCredentialKey(repoData)
	if err != nil {
		return nil, err
	}
	creds := models.GitCredentials{}
	data, err := azsecret.getSecretValue(ctx, key)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	json.Unmarshal([]byte(*data), creds)
	return &creds, nil
}

func (azsecret AzureSecretManager) getSecretValue(ctx context.Context, key string) (*string, error) {
	//azsecret.secretClient.
	response, err := azsecret.secretClient.GetSecret(ctx, key, "", nil)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	value := strings.Clone(*response.Value)
	return &value, nil
}

func (azsecret AzureSecretManager) FetchSecret(ctx context.Context, repoData *models.RepoData, name string) (*string, error) {
	key, err := getSecretKey(repoData, name)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return azsecret.getSecretValue(ctx, key)
}

var keyPattern = regexp.MustCompile(`([0-9a-zA-Z-]+)`)

func splitPythonLike(pattern *regexp.Regexp, s string) []string {
	var result []string
	offset := 0
	allowed := pattern.FindAllStringIndex(s, -1)
	for _, valid := range allowed {
		result = append(result, s[offset:valid[0]], s[valid[0]:valid[1]])
		offset = valid[1]
	}
	if offset != len(s) {
		result = append(result, s[offset:])
	}
	return result
}

// mirrored from dstack.backend.azure.secrets._encode
func encode(key string) string {
	var result []string
	isOutOfRange := true
	for _, chunk := range splitPythonLike(keyPattern, key) {
		if isOutOfRange {
			for _, c := range chunk {
				if c < 128 {
					result = append(result, "-")
				} else {
					result = append(result, fmt.Sprintf("%c", c))
				}
			}
		} else {
			result = append(result, chunk)
		}
		isOutOfRange = !isOutOfRange
	}
	return strings.Join(result, "")
}

func getSecretKey(repoData *models.RepoData, name string) (string, error) {
	// XXX: sync default value for sep with python's cli implementation.
	key := fmt.Sprintf("dstack-secrets-%s-%s", repoData.RepoDataPath("/"), name)
	value, err := puny.Encode(encode(key))
	if err != nil {
		return "", err
	}
	return value, nil
}

func getCredentialKey(repoData *models.RepoData) (string, error) {
	// XXX: sync default value for sep with python's cli implementation.
	key := fmt.Sprintf("dstack-credentials-%s", repoData.RepoDataPath("/"))
	value, err := puny.Encode(encode(key))
	if err != nil {
		return "", err
	}
	return value, nil
}
