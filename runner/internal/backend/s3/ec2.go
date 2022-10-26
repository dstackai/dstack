package local

import (
	"context"
	"io/ioutil"

	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/ec2/imds"
	"github.com/aws/aws-sdk-go-v2/service/ec2"
	"github.com/dstackai/dstackai/runner/internal/gerrors"
	"github.com/dstackai/dstackai/runner/internal/log"
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
	id, err := ec.getInstanceID(ctx)
	if err != nil {
		return gerrors.Wrap(err)
	}
	_, err = ec.cli.CancelSpotInstanceRequests(ctx, &ec2.CancelSpotInstanceRequestsInput{
		SpotInstanceRequestIds: []string{requestID},
	})
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
func (ec *ClientEC2) getInstanceID(ctx context.Context) (string, error) {
	meta, err := ec.metaCli.GetMetadata(ctx, &imds.GetMetadataInput{Path: "instance-id"})
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	id, err := ioutil.ReadAll(meta.Content)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	return string(id), nil
}
