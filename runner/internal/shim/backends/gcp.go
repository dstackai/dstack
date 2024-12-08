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

// Resolves device names according to https://cloud.google.com/compute/docs/disks/disk-symlinks
// The server registers device name as pd-{volumeID}
func (e *GCPBackend) GetRealDeviceName(volumeID string) (string, error) {
	// Try resolving first partition or external volumes
	deviceName, err := os.Readlink(fmt.Sprintf("/dev/disk/by-id/google-pd-%s-part1", volumeID))
	if err != nil {
		deviceName, err = os.Readlink(fmt.Sprintf("/dev/disk/by-id/google-pd-%s", volumeID))
		if err != nil {
			return "", fmt.Errorf("failed to resolve symlink for volume %s: %w", volumeID, err)
		}
	}
	deviceName, err = filepath.Abs(filepath.Join("/dev/disk/by-id/", deviceName))
	if err != nil {
		return "", tracerr.Wrap(err)
	}
	return deviceName, nil
}
