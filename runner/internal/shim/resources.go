package shim

import (
	"context"
	"errors"
	"fmt"
	"sync"

	"github.com/dstackai/dstack/runner/internal/log"
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
	// resource ID: locked mapping, where resource ID is vendor-specific:
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
			case host.GpuVendorTenstorrent:
				resourceID = gpu.Index
			case host.GpuVendorIntel:
				resourceID = gpu.Index
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

// Acquire returns a requested number of GPU resource IDs, marking them locked (busy)
// If there are not enough idle GPUs, none is locked and ErrNoCapacity is returned
// -1 means "all available GPUs", even if none, that is, Acquire(-1) never fails,
// even on hosts without GPU
// To release acquired GPUs, pass the returned resource IDs to Release() method
func (gl *GpuLock) Acquire(ctx context.Context, count int) ([]string, error) {
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

// Lock marks passed Resource IDs as locked (busy)
// This method never fails, it's safe to lock already locked resource or try to lock unknown resource
// The returned slice contains only actually locked resource IDs
func (gl *GpuLock) Lock(ctx context.Context, ids []string) []string {
	gl.mu.Lock()
	defer gl.mu.Unlock()
	lockedIDs := make([]string, 0, len(ids))
	for _, id := range ids {
		if locked, ok := gl.lock[id]; !ok {
			log.Warning(ctx, "skip locking: unknown GPU resource", "id", id)
		} else if locked {
			log.Info(ctx, "skip locking: GPU already locked", "id", id)
		} else {
			gl.lock[id] = true
			lockedIDs = append(lockedIDs, id)
		}
	}
	return lockedIDs
}

// Release marks passed Resource IDs as idle
// This method never fails, it's safe to release already idle resource or try to release unknown resource
// The returned slice contains only actually released resource IDs
func (gl *GpuLock) Release(ctx context.Context, ids []string) []string {
	gl.mu.Lock()
	defer gl.mu.Unlock()
	releasedIDs := make([]string, 0, len(ids))
	for _, id := range ids {
		if locked, ok := gl.lock[id]; !ok {
			log.Warning(ctx, "skip releasing: unknown GPU resource", "id", id)
		} else if !locked {
			log.Info(ctx, "skip releasing: GPU not locked", "id", id)
		} else {
			gl.lock[id] = false
			releasedIDs = append(releasedIDs, id)
		}
	}
	return releasedIDs
}
