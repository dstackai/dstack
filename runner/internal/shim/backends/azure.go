package backends

import (
	"context"
	"encoding/json"
	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/Azure/azure-sdk-for-go/sdk/resourcemanager/compute/armcompute/v4"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"net/http"
)

type AzureBackend struct {
	subscriptionId string
	resourceGroup  string
	vmName         string
}

func init() {
	register("azure", NewAzureBackend)
}

func NewAzureBackend(ctx context.Context) (Backend, error) {
	metadata, err := getAzureMetadata(ctx)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return &AzureBackend{
		subscriptionId: metadata.SubscriptionId,
		resourceGroup:  metadata.ResourceGroupName,
		vmName:         metadata.Name,
	}, nil
}

func (b *AzureBackend) Terminate(ctx context.Context) error {
	credential, err := azidentity.NewDefaultAzureCredential(nil)
	if err != nil {
		return gerrors.Wrap(err)
	}
	computeClient, err := armcompute.NewVirtualMachinesClient(b.subscriptionId, credential, nil)
	if err != nil {
		return gerrors.Wrap(err)
	}
	_, err = computeClient.BeginDelete(ctx, b.resourceGroup, b.vmName, nil)
	return gerrors.Wrap(err)
}

type AzureInstanceMetadata struct {
	SubscriptionId    string `json:"subscriptionId"`
	ResourceGroupName string `json:"resourceGroupName"`
	Name              string `json:"name"`
}

func getAzureMetadata(ctx context.Context) (*AzureInstanceMetadata, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, "http://169.254.169.254/metadata/instance?api-version=2021-02-01", nil)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	req.Header.Add("Metadata", "true")
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	decoder := json.NewDecoder(res.Body)
	var metadata AzureInstanceMetadata
	if err = decoder.Decode(&metadata); err != nil {
		return nil, gerrors.Wrap(err)
	}
	return &metadata, nil
}
