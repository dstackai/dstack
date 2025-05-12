package backends

type BackendVolumeOptions struct {
	DeviceName string // The name of the device, as expected by the `mount` command
	FsType     string // The `--type` argument for the `mount` command or "" to omit `--type`
}

type Backend interface {
	// GetVolumeOptions returns mount options for the given volume ID and virtual device name.
	GetVolumeOptions(volumeID, deviceName string) (*BackendVolumeOptions, error)
}
