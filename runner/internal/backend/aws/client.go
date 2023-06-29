package aws

import (
	"context"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

//var ErrTagNotFound = errors.New("tag not found")

type ClientS3 struct {
	cli *s3.Client
}

func NewClientS3(region string) *ClientS3 {
	c := new(ClientS3)
	ctx := context.TODO()
	cfg, err := config.LoadDefaultConfig(
		ctx,
		config.WithRegion(region),
	)
	if err != nil {
		return nil
	}
	c.cli = s3.NewFromConfig(cfg)
	return c
}
