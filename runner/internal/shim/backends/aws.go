package backends

import (
	"bytes"
	"fmt"
	"os"
	"os/exec"
	"strings"
)

type AWSBackend struct{}

func NewAWSBackend() *AWSBackend {
	return &AWSBackend{}
}

// GetRealDeviceName returns the device name for the given EBS volume ID and virtual deviceName.
// If the volume has no partitions, returns the volume device.
// If the volume has partitions, return the first partition device.
// The device name on the instance can be different from the device name specified in block-device mapping:
// * Nitro-based instances: /dev/sda => nvme0n1. lsblk returns volume-id in SERIAL.
// * Xen-based Ubuntu instances: /dev/sda => /dev/xvda.
// * Red Hat and CentOS: may increment trailing letters in some versions – not supported.
// * Other legacy systems: /dev/sda => /dev/sda.
// More: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/device_naming.html
func (e *AWSBackend) GetRealDeviceName(volumeID, deviceName string) (string, error) {
	// Run the lsblk command to get block device information
	// On AWS, SERIAL contains volume id.
	cmd := exec.Command("lsblk", "-o", "NAME,SERIAL")
	var out bytes.Buffer
	cmd.Stdout = &out
	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("failed to list block devices: %w", err)
	}

	baseDevice := ""

	// Parse the output to find the device that matches the volume ID
	lines := strings.Split(out.String(), "\n")
	for _, line := range lines {
		fields := strings.Fields(line)
		if len(fields) == 2 && strings.HasPrefix(fields[1], "vol") {
			serial := strings.TrimPrefix(fields[1], "vol")
			if "vol-"+serial == volumeID {
				baseDevice = "/dev/" + fields[0]
			}
		}
	}

	// If no match is found, fall back to mapping AWS device name
	if baseDevice == "" && deviceName != "" {
		// Try mapping deviceName to possible OS device names
		mappedDevices := []string{
			deviceName,
			strings.Replace(deviceName, "/dev/sd", "/dev/xvd", 1), // sdX => xvdX
		}
		for _, dev := range mappedDevices {
			if _, err := os.Stat(dev); err == nil {
				baseDevice = dev
				break
			}
		}
	}

	if baseDevice == "" {
		return "", fmt.Errorf("volume %s not found among block devices", volumeID)
	}

	// Run lsblk again to check for partitions on the base device
	cmd = exec.Command("lsblk", "-ln", "-o", "NAME", baseDevice)
	out.Reset()
	cmd.Stdout = &out
	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("failed to list partitions for device %s: %w", baseDevice, err)
	}
	partitions := strings.Split(strings.TrimSpace(out.String()), "\n")
	if len(partitions) > 1 {
		return "/dev/" + partitions[1], nil
	}

	return baseDevice, nil
}
