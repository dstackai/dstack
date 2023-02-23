package gcp

import (
	"context"
	"strings"

	compute "cloud.google.com/go/compute/apiv1"
	"cloud.google.com/go/compute/apiv1/computepb"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
)

type GCPCompute struct {
	instancesClient *compute.InstancesClient
	project         string
	zone            string
}

func NewGCPCompute(project, zone string) *GCPCompute {
	ctx := context.TODO()
	instancesClient, err := compute.NewInstancesRESTClient(ctx)
	if err != nil {
		return nil
	}
	return &GCPCompute{
		instancesClient: instancesClient,
		project:         project,
		zone:            zone,
	}
}

func (gcompute *GCPCompute) TerminateInstance(ctx context.Context, instanceID string) error {
	log.Trace(ctx, "Terminate instance", "ID", instanceID)
	req := &computepb.DeleteInstanceRequest{
		Instance: instanceID,
		Project:  gcompute.project,
		Zone:     gcompute.zone,
	}
	_, err := gcompute.instancesClient.Delete(ctx, req)
	if err != nil {
		if strings.Contains(err.Error(), "Error 404") {
			return nil
		}
		return gerrors.Wrap(err)
	}
	return nil
}
