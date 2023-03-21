package azure

import (
	"context"

	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/Azure/azure-sdk-for-go/sdk/resourcemanager/compute/armcompute/v4"
	"github.com/dstackai/dstack/runner/internal/gerrors"
)

type AzureCompute struct {
	client        armcompute.VirtualMachinesClient
	resourceGroup string
}

func NewAzureCompute(credential *azidentity.DefaultAzureCredential, subscriptionId, resourceGroup string) (*AzureCompute, error) {
	client, err := armcompute.NewVirtualMachinesClient(subscriptionId, credential, nil)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return &AzureCompute{client: *client, resourceGroup: resourceGroup}, nil
}

func (azcompute AzureCompute) TerminateInstance(ctx context.Context, requestID string) error {
	_, err := azcompute.client.BeginDelete(ctx, azcompute.resourceGroup, requestID, nil)
	if err != nil {
		return err
	}
	return nil
}
