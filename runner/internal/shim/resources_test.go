package shim

import (
	"context"
	"testing"

	"github.com/dstackai/dstack/runner/internal/common"
	"github.com/dstackai/dstack/runner/internal/shim/host"
	"github.com/stretchr/testify/assert"
)

func TestNewGpuLock_NoGpus(t *testing.T) {
	var gpus []host.GpuInfo
	gl, err := NewGpuLock(gpus)
	assert.Nil(t, err)
	assert.Equal(t, map[string]bool{}, gl.lock)
}

func TestNewGpuLock_NvidiaGpus(t *testing.T) {
	gpus := []host.GpuInfo{
		{Vendor: common.GpuVendorNvidia, ID: "GPU-beef"},
		{Vendor: common.GpuVendorNvidia, ID: "GPU-f00d"},
	}
	gl, err := NewGpuLock(gpus)
	assert.Nil(t, err)
	expected := map[string]bool{
		"GPU-beef": false,
		"GPU-f00d": false,
	}
	assert.Equal(t, expected, gl.lock)
}

func TestNewGpuLock_AmdGpus(t *testing.T) {
	gpus := []host.GpuInfo{
		{Vendor: common.GpuVendorAmd, RenderNodePath: "/dev/dri/renderD128"},
		{Vendor: common.GpuVendorAmd, RenderNodePath: "/dev/dri/renderD129"},
	}
	gl, err := NewGpuLock(gpus)
	assert.Nil(t, err)
	expected := map[string]bool{
		"/dev/dri/renderD128": false,
		"/dev/dri/renderD129": false,
	}
	assert.Equal(t, expected, gl.lock)
}

func TestNewGpuLock_ErrorMultipleVendors(t *testing.T) {
	gpus := []host.GpuInfo{
		{Vendor: common.GpuVendorAmd},
		{Vendor: common.GpuVendorNvidia},
	}
	gl, err := NewGpuLock(gpus)
	assert.Nil(t, gl)
	assert.ErrorContains(t, err, "multiple GPU vendors")
}

func TestGpuLock_Acquire_ErrorBadCount(t *testing.T) {
	gl, _ := NewGpuLock([]host.GpuInfo{})

	ids, err := gl.Acquire(context.Background(), 0)
	assert.ErrorContains(t, err, "count must be either positive or -1, got 0")
	assert.Equal(t, 0, len(ids))

	ids, err = gl.Acquire(context.Background(), -2)
	assert.ErrorContains(t, err, "count must be either positive or -1, got -2")
	assert.Equal(t, 0, len(ids))
}

func TestGpuLock_Acquire_All_Available(t *testing.T) {
	gpus := []host.GpuInfo{
		{Vendor: common.GpuVendorNvidia, ID: "GPU-beef"},
		{Vendor: common.GpuVendorNvidia, ID: "GPU-f00d"},
		{Vendor: common.GpuVendorNvidia, ID: "GPU-c0de"},
	}
	gl, _ := NewGpuLock(gpus)
	gl.lock["GPU-f00d"] = true
	ids, err := gl.Acquire(context.Background(), -1)
	assert.Nil(t, err)
	assert.ElementsMatch(t, []string{"GPU-beef", "GPU-c0de"}, ids)
	assert.True(t, gl.lock["GPU-beef"], "GPU-beef")
	assert.True(t, gl.lock["GPU-f00d"], "GPU-f00d")
	assert.True(t, gl.lock["GPU-c0de"], "GPU-c0de")
}

func TestGpuLock_Acquire_All_NoneAvailable(t *testing.T) {
	gpus := []host.GpuInfo{
		{Vendor: common.GpuVendorNvidia, ID: "GPU-beef"},
		{Vendor: common.GpuVendorNvidia, ID: "GPU-f00d"},
	}
	gl, _ := NewGpuLock(gpus)
	gl.lock["GPU-beef"] = true
	gl.lock["GPU-f00d"] = true
	ids, err := gl.Acquire(context.Background(), -1)
	assert.Nil(t, err)
	assert.Equal(t, 0, len(ids))
}

func TestGpuLock_Acquire_All_NoGpus(t *testing.T) {
	gl, _ := NewGpuLock([]host.GpuInfo{})
	ids, err := gl.Acquire(context.Background(), -1)
	assert.Nil(t, err)
	assert.Equal(t, 0, len(ids))
}

func TestGpuLock_Acquire_Count_OK(t *testing.T) {
	gpus := []host.GpuInfo{
		{Vendor: common.GpuVendorNvidia, ID: "GPU-beef"},
		{Vendor: common.GpuVendorNvidia, ID: "GPU-f00d"},
		{Vendor: common.GpuVendorNvidia, ID: "GPU-c0de"},
		{Vendor: common.GpuVendorNvidia, ID: "GPU-cafe"},
	}
	gl, _ := NewGpuLock(gpus)
	gl.lock["GPU-f00d"] = true
	ids, err := gl.Acquire(context.Background(), 2)
	assert.Nil(t, err)
	assert.Equal(t, 2, len(ids))
	assert.NotEqual(t, ids[0], ids[1])
	assert.NotContains(t, ids, "GPU-f00d")
	for id, locked := range gl.lock {
		switch id {
		case "GPU-f00d", ids[0], ids[1]:
			assert.True(t, locked, id)
		default:
			assert.False(t, locked, id)
		}
	}
}

func TestGpuLock_Acquire_Count_ErrNoCapacity(t *testing.T) {
	gpus := []host.GpuInfo{
		{Vendor: common.GpuVendorNvidia, ID: "GPU-beef"},
		{Vendor: common.GpuVendorNvidia, ID: "GPU-f00d"},
	}
	gl, _ := NewGpuLock(gpus)
	gl.lock["GPU-f00d"] = true
	ids, err := gl.Acquire(context.Background(), 2)
	assert.ErrorContains(t, err, "2 GPUs requested, 1 available")
	assert.Equal(t, 0, len(ids))
	assert.False(t, gl.lock["GPU-beef"], "GPU-beef")
	assert.True(t, gl.lock["GPU-f00d"], "GPU-f00d")
}

func TestGpuLock_Lock(t *testing.T) {
	gpus := []host.GpuInfo{
		{Vendor: common.GpuVendorNvidia, ID: "GPU-beef"},
		{Vendor: common.GpuVendorNvidia, ID: "GPU-f00d"},
		{Vendor: common.GpuVendorNvidia, ID: "GPU-c0de"},
	}
	gl, _ := NewGpuLock(gpus)
	gl.lock["GPU-beef"] = true
	gl.lock["GPU-f00d"] = true
	locked := gl.Lock(context.Background(), []string{
		"GPU-beef", // already locked
		"GPU-dead", // unknown
		"GPU-c0de", // not locked
	})
	assert.Equal(t, []string{"GPU-c0de"}, locked)
	assert.True(t, gl.lock["GPU-beef"], "GPU-beef") // was already locked
	assert.True(t, gl.lock["GPU-f00d"], "GPU-f00d") // was already locked
	assert.True(t, gl.lock["GPU-c0de"], "GPU-c0de") // has been locked
}

func TestGpuLock_Lock_Nil(t *testing.T) {
	gpus := []host.GpuInfo{
		{Vendor: common.GpuVendorNvidia, ID: "GPU-beef"},
		{Vendor: common.GpuVendorNvidia, ID: "GPU-f00d"},
	}
	gl, _ := NewGpuLock(gpus)
	gl.lock["GPU-beef"] = true
	var ids []string
	locked := gl.Lock(context.Background(), ids)
	assert.Equal(t, []string{}, locked)
	assert.True(t, gl.lock["GPU-beef"], "GPU-beef")
	assert.False(t, gl.lock["GPU-f00d"], "GPU-f00d")
}

func TestGpuLock_Release(t *testing.T) {
	gpus := []host.GpuInfo{
		{Vendor: common.GpuVendorNvidia, ID: "GPU-beef"},
		{Vendor: common.GpuVendorNvidia, ID: "GPU-f00d"},
		{Vendor: common.GpuVendorNvidia, ID: "GPU-c0de"},
	}
	gl, _ := NewGpuLock(gpus)
	gl.lock["GPU-beef"] = true
	gl.lock["GPU-f00d"] = true
	released := gl.Release(context.Background(), []string{
		"GPU-beef", // locked
		"GPU-dead", // unknown
		"GPU-c0de", // not locked
	})
	assert.Equal(t, []string{"GPU-beef"}, released)
	assert.False(t, gl.lock["GPU-beef"], "GPU-beef") // has been unlocked
	assert.True(t, gl.lock["GPU-f00d"], "GPU-f00d")  // still locked
	assert.False(t, gl.lock["GPU-c0de"], "GPU-c0de") // was already unlocked
}

func TestGpuLock_Release_Nil(t *testing.T) {
	gpus := []host.GpuInfo{
		{Vendor: common.GpuVendorNvidia, ID: "GPU-beef"},
		{Vendor: common.GpuVendorNvidia, ID: "GPU-f00d"},
	}
	gl, _ := NewGpuLock(gpus)
	gl.lock["GPU-beef"] = true
	var ids []string
	released := gl.Release(context.Background(), ids)
	assert.Equal(t, []string{}, released)
	assert.True(t, gl.lock["GPU-beef"], "GPU-beef")
	assert.False(t, gl.lock["GPU-f00d"], "GPU-f00d")
}
