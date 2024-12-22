package backends

type Backend interface {
	// GetRealDeviceName returns the real device name for the given volume ID and virtual device name.
	GetRealDeviceName(volumeID, deviceName string) (string, error)
}
