package shim

import (
	"errors"
	"fmt"
	"log"
	"sync"

	"github.com/dstackai/dstack/runner/internal/shim/host"
)

var ErrNoCapacity = errors.New("no capacity")

type Resources struct {
	Gpus         []host.GpuInfo
	CpuCount     int
	TotalMemory  uint64 // bytes
	DiskSize     uint64 // bytes
	NetAddresses []string
}

type GpuLock struct {
	// resourceID: locked mapping, where resourceID is vendor-specific:
	// NVIDIA: host.GpuInfo.ID
	// AMD: host.GpuInfo.RenderNodePath
	lock map[string]bool
	mu   sync.Mutex
}

func NewGpuLock(gpus []host.GpuInfo) (*GpuLock, error) {
	lock := make(map[string]bool, len(gpus))
	if len(gpus) > 0 {
		vendor := gpus[0].Vendor
		for _, gpu := range gpus {
			if gpu.Vendor != vendor {
				return nil, errors.New("multiple GPU vendors detected")
			}
			var resourceID string
			switch vendor {
			case host.GpuVendorNvidia:
				resourceID = gpu.ID
			case host.GpuVendorAmd:
				resourceID = gpu.RenderNodePath
			case host.GpuVendorNone:
				return nil, fmt.Errorf("unexpected GPU vendor %s", vendor)
			default:
				return nil, fmt.Errorf("unexpected GPU vendor %s", vendor)
			}
			lock[resourceID] = false
		}
	}
	return &GpuLock{lock: lock}, nil
}

func (gl *GpuLock) Acquire(count int) ([]string, error) {
	// -1 means all available, even if none, that is, Acquire(-1) never fails, even on hosts without GPU
	if count == 0 || count < -1 {
		return nil, fmt.Errorf("count must be either positive or -1, got %d", count)
	}
	gl.mu.Lock()
	defer gl.mu.Unlock()
	var size int
	if count > 0 {
		size = count
	} else {
		size = len(gl.lock)
	}
	ids := make([]string, 0, size)
	for id, locked := range gl.lock {
		if !locked {
			ids = append(ids, id)
		}
		if count > 0 && len(ids) >= count {
			break
		}
	}
	if len(ids) < count {
		return nil, fmt.Errorf("%w: %d GPUs requested, %d available", ErrNoCapacity, count, len(ids))
	}
	for _, id := range ids {
		gl.lock[id] = true
	}
	return ids, nil
}

func (gl *GpuLock) Release(ids []string) {
	gl.mu.Lock()
	defer gl.mu.Unlock()
	for _, id := range ids {
		if locked, ok := gl.lock[id]; !ok {
			log.Printf("skipping %s: unknown GPU resource", id)
		} else if !locked {
			log.Printf("skipping %s: not locked", id)
		} else {
			gl.lock[id] = false
		}
	}
}
