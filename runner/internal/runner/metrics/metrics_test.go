package metrics

import (
	"os"
	"path"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/dstackai/dstack/runner/internal/common/gpu"
	"github.com/dstackai/dstack/runner/internal/runner/schemas"
)

func TestGetSystemMetrics_ContainerRoot(t *testing.T) {
	mountPoint := t.TempDir()
	for name, content := range map[string]string{
		"cpu.stat":       "usage_usec 12345\nuser_usec 12000\nsystem_usec 345\n",
		"memory.current": "8192\n",
		"memory.stat":    "anon 6144\ninactive_file 2048\n",
	} {
		require.NoError(t, os.WriteFile(path.Join(mountPoint, name), []byte(content), 0o600))
	}
	collector := &MetricsCollector{cgroupMountPoint: mountPoint, gpuVendor: gpu.GpuVendorNone}
	metrics, err := collector.GetSystemMetrics(t.Context())
	require.NoError(t, err)
	require.Equal(t, uint64(12345), metrics.CpuUsage)
	require.Equal(t, uint64(8192), metrics.MemoryUsage)
	require.Equal(t, uint64(6144), metrics.MemoryWorkingSet)
	require.Empty(t, metrics.GPUMetrics)
}

func TestGetAMDGPUMetrics_OK(t *testing.T) {
	collector, err := NewMetricsCollector(t.Context())
	assert.NoError(t, err)

	cases := []struct {
		csv      string
		expected []schemas.GPUMetrics
	}{
		// AMDSMI Tool: 24.7.1+0012a68 | AMDSMI Library version: 24.7.1.0 | ROCm version: 6.3.1
		{
			csv: "gpu,gfx,gfx_clock,vram_used,vram_total\n0,10,132,283,196300\n",
			expected: []schemas.GPUMetrics{
				{GPUUtil: 10, GPUMemoryUsage: 296747008},
			},
		},
		// AMDSMI Tool: 25.3.0+ede62f2 | AMDSMI Library version: 25.3.0 | ROCm version: 6.4.0
		{
			csv: "gpu,gfx_clk,gfx,vram_used,vram_free,vram_total,vram_percent\n0,132,10,283,196309,196592,0.0\n",
			expected: []schemas.GPUMetrics{
				{GPUUtil: 10, GPUMemoryUsage: 296747008},
			},
		},
	}

	for _, tc := range cases {
		metrics, err := collector.getAMDGPUMetrics(tc.csv)
		assert.NoError(t, err)
		assert.Equal(t, tc.expected, metrics)
	}
}

func TestGetAMDGPUMetrics_ErrorGPUUtilNA(t *testing.T) {
	collector, err := NewMetricsCollector(t.Context())
	assert.NoError(t, err)
	metrics, err := collector.getAMDGPUMetrics("gpu,gfx,gfx_clock,vram_used,vram_total\n0,N/A,N/A,283,196300\n")
	assert.ErrorContains(t, err, "GPU utilization is N/A")
	assert.Nil(t, metrics)
}
