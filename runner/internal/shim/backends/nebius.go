package backends

type NebiusBackend struct{}

func NewNebiusBackend() *NebiusBackend {
	return &NebiusBackend{}
}

// https://docs.nebius.com/compute/storage/use#mount-filesystems
func (e *NebiusBackend) GetVolumeOptions(volumeID, deviceName string) (*BackendVolumeOptions, error) {
	return &BackendVolumeOptions{
		DeviceName: deviceName,
		FsType:     "virtiofs",
	}, nil
}
