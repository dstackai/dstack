package backends

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"

	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/Azure/azure-sdk-for-go/sdk/resourcemanager/compute/armcompute/v4"
	"github.com/dstackai/dstack/runner/internal/gerrors"
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
	metadata, err := getAzureMetadata(ctx, nil)
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
	credential, err := azidentity.NewManagedIdentityCredential(nil)
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

type AzureComputeInstanceMetadata struct {
	SubscriptionId    string `json:"subscriptionId"`
	ResourceGroupName string `json:"resourceGroupName"`
	Name              string `json:"name"`
}

type AzureInstanceMetadata struct {
	Compute AzureComputeInstanceMetadata `json:"compute"`
}

func getAzureMetadata(ctx context.Context, url *string) (*AzureComputeInstanceMetadata, error) {
	baseURL := "http://169.254.169.254"
	if url != nil {
		baseURL = *url
	}
	req, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		fmt.Sprintf("%s/metadata/instance?api-version=2021-02-01", baseURL),
		nil,
	)
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
	return &metadata.Compute, nil
}
