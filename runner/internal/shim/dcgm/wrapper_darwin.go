//go:build darwin

package dcgm

import "errors"

func NewDCGMWrapper(address string) (DCGMWrapperInterface, error) {
	return nil, errors.New("macOS is not supported")
}
