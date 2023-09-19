package backends

import (
	"bytes"
	"context"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/feature/ec2/imds"
	"github.com/aws/aws-sdk-go-v2/service/ec2"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"io"
)

type AWSBackend struct {
	region     string
	instanceId string
	spot       bool
}

func init() {
	register("aws", NewAWSBackend)
}

func NewAWSBackend(ctx context.Context) (Backend, error) {
	cfg, err := config.LoadDefaultConfig(ctx)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}

	client := imds.NewFromConfig(cfg)
	region, err := client.GetRegion(ctx, &imds.GetRegionInput{})
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	lifecycle, err := getMetadata(ctx, client, "instance-life-cycle")
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	instanceId, err := getMetadata(ctx, client, "instance-id")
	if err != nil {
		return nil, gerrors.Wrap(err)
	}

	return &AWSBackend{
		region:     region.Region,
		instanceId: instanceId,
		spot:       lifecycle == "spot",
	}, nil
}

func (b *AWSBackend) Terminate(ctx context.Context) error {
	cfg, err := config.LoadDefaultConfig(ctx, config.WithRegion(b.region))
	if err != nil {
		return gerrors.Wrap(err)
	}
	client := ec2.NewFromConfig(cfg)
	_, err = client.TerminateInstances(ctx, &ec2.TerminateInstancesInput{
		InstanceIds: []string{b.instanceId},
	})
	return gerrors.Wrap(err)
}

func getMetadata(ctx context.Context, client *imds.Client, path string) (string, error) {
	resp, err := client.GetMetadata(ctx, &imds.GetMetadataInput{
		Path: path,
	})
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	var b bytes.Buffer
	if _, err = io.Copy(&b, resp.Content); err != nil {
		return "", err
	}
	return b.String(), nil
}
