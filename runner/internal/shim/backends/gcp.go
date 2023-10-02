package backends

import (
	compute "cloud.google.com/go/compute/apiv1"
	"cloud.google.com/go/compute/apiv1/computepb"
	"context"
	"fmt"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"io"
	"net/http"
	"strings"
)

type GCPBackend struct {
	instanceName string
	project      string
	zone         string
}

func init() {
	register("gcp", NewGCPBackend)
}

func NewGCPBackend(ctx context.Context) (Backend, error) {
	instanceName, err := getGCPMetadata(ctx, "/instance/name")
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	projectZone, err := getGCPMetadata(ctx, "/instance/zone")
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	// Parse `projects/<project-id>/zones/<projectZone>`
	parts := strings.Split(projectZone, "/")
	return &GCPBackend{
		instanceName: instanceName,
		project:      parts[1],
		zone:         parts[3],
	}, nil
}

func (b *GCPBackend) Terminate(ctx context.Context) error {
	instancesClient, err := compute.NewInstancesRESTClient(ctx)
	if err != nil {
		return nil
	}
	req := &computepb.DeleteInstanceRequest{
		Instance: b.instanceName,
		Project:  b.project,
		Zone:     b.zone,
	}
	_, err = instancesClient.Delete(ctx, req)
	return gerrors.Wrap(err)
}

func getGCPMetadata(ctx context.Context, path string) (string, error) {
	req, err := http.NewRequest(http.MethodGet, fmt.Sprintf("http://metadata.google.internal/computeMetadata/v1%s", path), nil)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	req.Header.Add("Metadata-Flavor", "Google")
	res, err := http.DefaultClient.Do(req.WithContext(ctx))
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	body, err := io.ReadAll(res.Body)
	if err != nil {
		return "", gerrors.Wrap(err)
	}
	return string(body), nil
}
