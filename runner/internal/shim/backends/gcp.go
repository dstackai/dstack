package backends

import (
	"context"
	"fmt"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"io"
	"net/http"
)

type GCPBackend struct {
	instanceName string
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
	zone, err := getGCPMetadata(ctx, "/instance/zone")
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return &GCPBackend{
		instanceName: instanceName,
		zone:         zone,
	}, nil
}

func (b *GCPBackend) Terminate(ctx context.Context) error {
	req, err := http.NewRequest(http.MethodDelete, fmt.Sprintf("https://compute.googleapis.com/compute/v1/%s/instances/%s", b.zone, b.instanceName), nil)
	if err != nil {
		return gerrors.Wrap(err)
	}
	_, err = http.DefaultClient.Do(req.WithContext(ctx))
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
