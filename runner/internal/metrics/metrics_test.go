package metrics

import (
	"runtime"
	"testing"

	"github.com/dstackai/dstack/runner/internal/schemas"
	"github.com/stretchr/testify/assert"
)

func TestGetAMDGPUMetrics_OK(t *testing.T) {
	if runtime.GOOS == "darwin" {
		t.Skip("Skipping on macOS")
	}
	collector, err := NewMetricsCollector()
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
	if runtime.GOOS == "darwin" {
		t.Skip("Skipping on macOS")
	}
	collector, err := NewMetricsCollector()
	assert.NoError(t, err)
	metrics, err := collector.getAMDGPUMetrics("gpu,gfx,gfx_clock,vram_used,vram_total\n0,N/A,N/A,283,196300\n")
	assert.ErrorContains(t, err, "GPU utilization is N/A")
	assert.Nil(t, metrics)
}
