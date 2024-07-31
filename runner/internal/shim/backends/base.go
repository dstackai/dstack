package backends

type Backend interface {
	// GetRealDeviceName returns the device name for the given volume ID.
	GetRealDeviceName(volumeID string) (string, error)
}