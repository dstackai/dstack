package azure

import (
	"context"
	"github.com/Azure/azure-sdk-for-go/sdk/azcore/to"
	"strings"

	"github.com/Azure/azure-sdk-for-go/sdk/azidentity"
	"github.com/Azure/azure-sdk-for-go/sdk/resourcemanager/compute/armcompute/v4"
	"github.com/Azure/azure-sdk-for-go/sdk/resourcemanager/network/armnetwork/v2"
	"github.com/dstackai/dstack/runner/internal/gerrors"
)

type AzureCompute struct {
	computeClient    armcompute.VirtualMachinesClient
	interfacesClient armnetwork.InterfacesClient
	ipAddressClient  armnetwork.PublicIPAddressesClient
	resourceGroup    string
}

func NewAzureCompute(credential *azidentity.DefaultAzureCredential, subscriptionId, resourceGroup string) (*AzureCompute, error) {
	computeClient, err := armcompute.NewVirtualMachinesClient(subscriptionId, credential, nil)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	interfacesClient, err := armnetwork.NewInterfacesClient(subscriptionId, credential, nil)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	ipAddressClient, err := armnetwork.NewPublicIPAddressesClient(subscriptionId, credential, nil)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return &AzureCompute{
		computeClient:    *computeClient,
		interfacesClient: *interfacesClient,
		ipAddressClient:  *ipAddressClient,
		resourceGroup:    resourceGroup,
	}, nil
}

func (azcompute AzureCompute) GetInstancePublicIP(ctx context.Context, requestID string) (string, error) {
	resp, err := azcompute.computeClient.Get(ctx, azcompute.resourceGroup, requestID, nil)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	interfaceID := *resp.VirtualMachine.Properties.NetworkProfile.NetworkInterfaces[0].ID
	interfaceName := getNetworkInterfaceName(interfaceID)
	networkInterface, err := azcompute.interfacesClient.Get(ctx, azcompute.resourceGroup, interfaceName, &armnetwork.InterfacesClientGetOptions{Expand: to.Ptr("IPConfigurations/PublicIPAddress")})
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	return *networkInterface.Properties.IPConfigurations[0].Properties.PublicIPAddress.Properties.IPAddress, nil
}

func (azcompute AzureCompute) TerminateInstance(ctx context.Context, requestID string) error {
	_, err := azcompute.computeClient.BeginDelete(ctx, azcompute.resourceGroup, requestID, nil)
	if err != nil {
		return err
	}
	return nil
}

func getNetworkInterfaceName(networkInterfaceID string) string {
	parts := strings.Split(networkInterfaceID, "/")
	return parts[len(parts)-1]
}
