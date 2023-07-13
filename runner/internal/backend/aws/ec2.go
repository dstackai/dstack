package aws

import (
	"context"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/ec2/imds"
	"github.com/aws/aws-sdk-go-v2/service/ec2"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"io"
)

type ClientEC2 struct {
	cli     *ec2.Client
	metaCli *imds.Client
}

func NewClientEC2(region string) *ClientEC2 {
	c := new(ClientEC2)
	ctx := context.TODO()
	cfg, err := config.LoadDefaultConfig(
		ctx,
		config.WithRegion(region),
	)
	if err != nil {
		return nil
	}
	c.cli = ec2.NewFromConfig(cfg)
	c.metaCli = imds.NewFromConfig(cfg)
	return c
}

func (ec *ClientEC2) CancelSpot(ctx context.Context, requestID string) error {
	log.Trace(ctx, "Cancel spot instance", "ID", requestID)
	_, err := ec.cli.CancelSpotInstanceRequests(ctx, &ec2.CancelSpotInstanceRequestsInput{
		SpotInstanceRequestIds: []string{requestID},
	})
	if err != nil {
		return gerrors.Wrap(err)
	}
	id, err := ec.getInstanceID(ctx)
	if err != nil {
		return gerrors.Wrap(err)
	}
	log.Trace(ctx, "Terminate spot instance", "ID", id)
	_, err = ec.cli.TerminateInstances(ctx, &ec2.TerminateInstancesInput{
		InstanceIds: []string{id},
	})
	if err != nil {
		return gerrors.Wrap(err)
	}
	return nil
}

func (ec *ClientEC2) TerminateInstance(ctx context.Context, requestID string) error {
	log.Trace(ctx, "Terminate instance", "ID", requestID)
	_, err := ec.cli.TerminateInstances(ctx, &ec2.TerminateInstancesInput{
		InstanceIds: []string{requestID},
	})
	if err != nil {
		return gerrors.Wrap(err)
	}

	return nil
}

func (ec *ClientEC2) IsInterruptedSpot(ctx context.Context, requestID string) (bool, error) {
	log.Trace(ctx, "Checking if spot was interrupted", "RequestID", requestID)
	input := &ec2.DescribeSpotInstanceRequestsInput{
		SpotInstanceRequestIds: []string{requestID},
	}
	res, err := ec.cli.DescribeSpotInstanceRequests(ctx, input)
	if err != nil {
		return false, gerrors.Wrap(err)
	}
	if len(res.SpotInstanceRequests) == 0 {
		return false, nil
	}
	request := res.SpotInstanceRequests[0]
	switch *request.Status.Code {
	case "instance-stopped-by-price":
	case "instance-stopped-no-capacity":
	case "instance-terminated-by-price":
	case "instance-terminated-no-capacity":
	case "marked-for-stop":
	case "marked-for-termination":
	case "marked-for-stop-by-experiment":
	case "instance-stopped-by-experiment":
	case "instance-terminated-by-experiment":
		return true, nil
	}
	return false, nil
}

func (ec *ClientEC2) getInstanceID(ctx context.Context) (string, error) {
	meta, err := ec.metaCli.GetMetadata(ctx, &imds.GetMetadataInput{Path: "instance-id"})
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	id, err := io.ReadAll(meta.Content)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	return string(id), nil
}
