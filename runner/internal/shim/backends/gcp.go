package backends

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/ztrue/tracerr"
)

type GCPBackend struct{}

func NewGCPBackend() *GCPBackend {
	return &GCPBackend{}
}

// GetRealDeviceName resolves device names according to https://cloud.google.com/compute/docs/disks/disk-symlinks
func (e *GCPBackend) GetRealDeviceName(volumeID, deviceName string) (string, error) {
	// Try resolving first partition or external volumes
	realDeviceName, err := os.Readlink(fmt.Sprintf("/dev/disk/by-id/google-%s-part1", deviceName))
	if err != nil {
		realDeviceName, err = os.Readlink(fmt.Sprintf("/dev/disk/by-id/google-%s", deviceName))
		if err != nil {
			return "", fmt.Errorf("failed to resolve symlink for volume %s: %w", volumeID, err)
		}
	}
	realDeviceName, err = filepath.Abs(filepath.Join("/dev/disk/by-id/", realDeviceName))
	if err != nil {
		return "", tracerr.Wrap(err)
	}
	return realDeviceName, nil
}
