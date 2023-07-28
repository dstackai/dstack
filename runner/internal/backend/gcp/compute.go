package gcp

import (
	"context"
	"io"
	"net/http"
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

func (gcompute *GCPCompute) GetInstancePublicIP(ctx context.Context, instanceID string) (string, error) {
	log.Trace(ctx, "Getting GCP instance IP", "instanceID", instanceID)
	req := &computepb.GetInstanceRequest{
		Instance: instanceID,
		Project:  gcompute.project,
		Zone:     gcompute.zone,
	}
	instance, err := gcompute.instancesClient.Get(ctx, req)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	ip := instance.NetworkInterfaces[0].AccessConfigs[0].NatIP
	return *ip, nil
}

func (gcompute *GCPCompute) StopInstance(ctx context.Context, instanceID string) error {
	log.Trace(ctx, "Stop instance", "ID", instanceID)
	req := &computepb.StopInstanceRequest{
		Instance: instanceID,
		Project:  gcompute.project,
		Zone:     gcompute.zone,
	}
	_, err := gcompute.instancesClient.Stop(ctx, req)
	if err != nil {
		if strings.Contains(err.Error(), "Error 404") {
			return nil
		}
		return gerrors.Wrap(err)
	}
	return nil
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

func (gcompute *GCPCompute) IsInterruptedSpot(ctx context.Context, instanceID string) (bool, error) {
	log.Trace(ctx, "Checking if spot was interrupted", "ID", instanceID)
	req, err := http.NewRequest("GET", "http://metadata.google.internal/computeMetadata/v1/instance/preempted", nil)
	if err != nil {
		return false, err
	}
	req.Header.Add("Metadata-Flavor", "Google")
	client := http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return false, err
	}
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return false, err
	}
	return string(body) == "TRUE", nil
}
