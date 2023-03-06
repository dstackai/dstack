package azure

import (
	"context"
	"encoding/json"
	"fmt"
	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/Azure/azure-sdk-for-go/sdk/keyvault/azsecrets"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/models"
	"regexp"
	strings "strings"
)

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
	key := getCreadentialsKey(repoData)
	creds := models.GitCredentials{}
	data, err := azsecret.getSecretValue(ctx, key)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	json.Unmarshal([]byte(*data), creds)
	return &creds, nil
}

func (azsecret AzureSecretManager) getSecretValue(ctx context.Context, key string) (*string, error) {
	response, err := azsecret.secretClient.GetSecret(ctx, key, "", nil)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	value := strings.Clone(*response.Value)
	return &value, nil
}

var keyPattern *regexp.Regexp // = "([0-9a-zA-Z-]+)"

func init() {
	keyPattern = regexp.MustCompile(`([0-9a-zA-Z-]+)`)
}

// mirrored from dstack.backend.azure.secrets._encode
func encode(key string) string {
	var result []string
	isOutOfRange := true
	for _, chunk := range keyPattern.Split(key, -1) {
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

func getCreadentialsKey(repoData *models.RepoData) string {
	// XXX: sync default value for sep with python's cli implementation.
	key := fmt.Sprintf("dstack-credentials-%s", repoData.RepoDataPath("/"))
	return encode(key)
}
