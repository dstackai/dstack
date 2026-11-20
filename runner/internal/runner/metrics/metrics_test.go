package metrics

import (
	"encoding/json"
	"testing"

	"github.com/dstackai/dstack/runner/internal/runner/schemas"
	"github.com/stretchr/testify/assert"
)

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

func TestParseNVIDIASMILikeMetrics(t *testing.T) {
	watts := func(w float64) *float64 { return &w }

	cases := []struct {
		name      string
		output    string
		withPower bool
		expected  []schemas.GPUMetrics
	}{
		{
			// NVIDIA driver 620.70.06, Tesla T4 under load
			name:      "nvidia-smi",
			output:    "525, 100, 68.23, 70.00\n",
			withPower: true,
			expected: []schemas.GPUMetrics{
				{GPUMemoryUsage: 550502400, GPUUtil: 100, GPUPowerDraw: watts(68.23), GPUPowerLimit: watts(70)},
			},
		},
		{
			// the T4 at idle, then made-up lines for GPUs without power readings
			name: "nvidia-smi, GPUs without power readings",
			output: "525, 0, 26.88, 70.00\n1024, 5, [N/A], [N/A]\n2048, 7, [Not Supported], [Not Supported]\n" +
				"512, 9, [Unknown Error], 70.00\n256, 1, NaN, Inf\n",
			withPower: true,
			expected: []schemas.GPUMetrics{
				{GPUMemoryUsage: 550502400, GPUUtil: 0, GPUPowerDraw: watts(26.88), GPUPowerLimit: watts(70)},
				{GPUMemoryUsage: 1073741824, GPUUtil: 5},
				{GPUMemoryUsage: 2147483648, GPUUtil: 7},
				{GPUMemoryUsage: 536870912, GPUUtil: 9, GPUPowerLimit: watts(70)},
				{GPUMemoryUsage: 268435456, GPUUtil: 1},
			},
		},
		{
			name:   "hl-smi",
			output: "512, 3\n",
			expected: []schemas.GPUMetrics{
				{GPUMemoryUsage: 536870912, GPUUtil: 3},
			},
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			metrics, err := parseNVIDIASMILikeMetrics(tc.output, tc.withPower)
			assert.NoError(t, err)
			assert.Equal(t, tc.expected, metrics)
			// a value json.Marshal rejects would fail the whole metrics response
			_, err = json.Marshal(metrics)
			assert.NoError(t, err)
		})
	}
}
