//go:build darwin

package capabilities

import "errors"

type Capability string

const (
	SETUID       = Capability("SETUID")
	SETGID       = Capability("SETGID")
	CHOWN        = Capability("CHOWN")
	SYS_RESOURCE = Capability("SYS_RESOURCE")
)

func Has(c Capability) (bool, error) {
	return false, errors.New("not supported")
}

func Check(cs ...Capability) (missing []Capability, err error) {
	return nil, errors.New("not supported")
}
