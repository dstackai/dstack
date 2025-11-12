//go:build linux && !cgo

package dcgm

import "fmt"

func NewDCGMWrapper(address string) (DCGMWrapperInterface, error) {
	return nil, fmt.Errorf("DCGM unavailable: built with CGO disabled (cross-compilation)")
}
