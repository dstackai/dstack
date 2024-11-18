package backends

import (
	"bytes"
	"fmt"
	"os/exec"
	"strings"
)

type AWSBackend struct{}

func NewAWSBackend() *AWSBackend {
	return &AWSBackend{}
}

// GetRealDeviceName returns the device name for the given EBS volume ID.
// The device name on instance can be different from device name specified in block-device mapping
// (e.g. NVMe block devices built on the Nitro System).
func (e *AWSBackend) GetRealDeviceName(volumeID string) (string, error) {
	// Run the lsblk command to get block device information
	// On AWS, SERIAL contains volume id.
	cmd := exec.Command("lsblk", "-o", "NAME,SERIAL")
	var out bytes.Buffer
	cmd.Stdout = &out
	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("failed to list block devices: %w", err)
	}

	// Parse the output to find the device that matches the volume ID
	lines := strings.Split(out.String(), "\n")
	for _, line := range lines {
		fields := strings.Fields(line)
		if len(fields) == 2 && strings.HasPrefix(fields[1], "vol") {
			serial := strings.TrimPrefix(fields[1], "vol")
			if "vol-"+serial == volumeID {
				return "/dev/" + fields[0], nil
			}
		}
	}

	return "", fmt.Errorf("volume %s not found among block devices", volumeID)
}
