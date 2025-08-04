package host

import (
	"os"
	"path/filepath"
	"reflect"
	"strconv"
	"testing"

	"github.com/dstackai/dstack/runner/internal/common"
)

func loadTestData(filename string) ([]byte, error) {
	path := filepath.Join("testdata", filename)
	return os.ReadFile(path)
}

func TestUnmarshalTtSmiSnapshot(t *testing.T) {
	tests := []struct {
		name     string
		filename string
		want     *ttSmiSnapshot
		wantErr  bool
	}{
		{
			name:     "valid single device",
			filename: "tenstorrent/valid_single_device.json",
			want: &ttSmiSnapshot{
				DeviceInfo: []ttDeviceInfo{
					{
						BoardInfo: ttBoardInfo{
							BoardType: "n150 L",
							BoardID:   "100018611902010",
						},
					},
				},
			},
			wantErr: false,
		},
		{
			name:     "valid multiple devices",
			filename: "tenstorrent/valid_multiple_devices.json",
			want: &ttSmiSnapshot{
				DeviceInfo: []ttDeviceInfo{
					{
						BoardInfo: ttBoardInfo{
							BoardType: "n300 L",
							BoardID:   "10001451172208f",
						},
					},
					{
						BoardInfo: ttBoardInfo{
							BoardType: "n300 L",
							BoardID:   "100014511722053",
						},
					},
					{
						BoardInfo: ttBoardInfo{
							BoardType: "n300 L",
							BoardID:   "10001451172209c",
						},
					},
					{
						BoardInfo: ttBoardInfo{
							BoardType: "n300 L",
							BoardID:   "100014511722058",
						},
					},
					{
						BoardInfo: ttBoardInfo{
							BoardType: "n300 R",
							BoardID:   "10001451172208f",
						},
					},
					{
						BoardInfo: ttBoardInfo{
							BoardType: "n300 R",
							BoardID:   "100014511722053",
						},
					},
					{
						BoardInfo: ttBoardInfo{
							BoardType: "n300 R",
							BoardID:   "10001451172209c",
						},
					},
					{
						BoardInfo: ttBoardInfo{
							BoardType: "n300 R",
							BoardID:   "100014511722058",
						},
					},
				},
			},
			wantErr: false,
		},
		{
			name:     "empty device info",
			filename: "tenstorrent/empty_device_info.json",
			want: &ttSmiSnapshot{
				DeviceInfo: []ttDeviceInfo{},
			},
			wantErr: false,
		},
		{
			name:     "invalid JSON",
			filename: "tenstorrent/invalid_json.json",
			want:     nil,
			wantErr:  true,
		},
		{
			name:     "missing device_info field",
			filename: "tenstorrent/missing_device_info.json",
			want:     &ttSmiSnapshot{DeviceInfo: nil},
			wantErr:  false,
		},
		{
			name:     "empty JSON",
			filename: "tenstorrent/empty_json.json",
			want:     &ttSmiSnapshot{DeviceInfo: nil},
			wantErr:  false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			data, err := loadTestData(tt.filename)
			if err != nil {
				t.Fatalf("Failed to load test data from %s: %v", tt.filename, err)
			}

			got, err := unmarshalTtSmiSnapshot(data)
			if (err != nil) != tt.wantErr {
				t.Errorf("unmarshalTtSmiSnapshot() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !tt.wantErr {
				if got == nil {
					t.Errorf("unmarshalTtSmiSnapshot() returned nil, expected non-nil result")
					return
				}
				if len(got.DeviceInfo) != len(tt.want.DeviceInfo) {
					t.Errorf("unmarshalTtSmiSnapshot() device count = %v, want %v", len(got.DeviceInfo), len(tt.want.DeviceInfo))
					return
				}
				for i, device := range got.DeviceInfo {
					if i >= len(tt.want.DeviceInfo) {
						break
					}
					expected := tt.want.DeviceInfo[i]
					if device.BoardInfo.BoardType != expected.BoardInfo.BoardType {
						t.Errorf("unmarshalTtSmiSnapshot() device[%d].BoardInfo.BoardType = %v, want %v", i, device.BoardInfo.BoardType, expected.BoardInfo.BoardType)
					}
					if device.BoardInfo.BoardID != expected.BoardInfo.BoardID {
						t.Errorf("unmarshalTtSmiSnapshot() device[%d].BoardInfo.BoardID = %v, want %v", i, device.BoardInfo.BoardID, expected.BoardInfo.BoardID)
					}
				}
			}
		})
	}
}

func TestGetGpusFromTtSmiSnapshot(t *testing.T) {
	data, err := loadTestData("tenstorrent/single_n150_gpu.json")
	if err != nil {
		t.Fatalf("Failed to load test data: %v", err)
	}
	snapshot, err := unmarshalTtSmiSnapshot(data)
	if err != nil {
		t.Fatalf("Failed to unmarshal snapshot: %v", err)
	}

	expectedGpus := []GpuInfo{
		{
			Vendor: common.GpuVendorTenstorrent,
			Name:   "n150",
			Vram:   12 * 1024,
			ID:     "100018611902010",
			Index:  "0",
		},
	}

	gpus := getGpusFromTtSmiSnapshot(snapshot)

	if !reflect.DeepEqual(gpus, expectedGpus) {
		t.Errorf("getGpusFromTtSmiSnapshot() = %v, want %v", gpus, expectedGpus)
	}
}

func TestGetGpusFromTtSmiSnapshotMultipleDevices(t *testing.T) {
	data, err := loadTestData("tenstorrent/valid_multiple_devices.json")
	if err != nil {
		t.Fatalf("Failed to load test data: %v", err)
	}
	snapshot, err := unmarshalTtSmiSnapshot(data)
	if err != nil {
		t.Fatalf("Failed to unmarshal snapshot: %v", err)
	}

	gpus := getGpusFromTtSmiSnapshot(snapshot)

	// Verify we have 4 unique GPUs (grouped by board_id)
	if len(gpus) != 4 {
		t.Errorf("getGpusFromTtSmiSnapshot() returned %d GPUs, want 4", len(gpus))
	}

	// Create a map to check the results by board_id
	gpusByID := make(map[string]GpuInfo)
	for _, gpu := range gpus {
		gpusByID[gpu.ID] = gpu
	}

	// Verify specific GPUs and their aggregated VRAM
	expectedGpus := map[string]struct {
		name string
		vram int
	}{
		"10001451172208f": {"n300", 24 * 1024}, // 12GB (n300 L) + 12GB (n300 R) = 24GB
		"100014511722053": {"n300", 24 * 1024}, // 12GB (n300 L) + 12GB (n300 R) = 24GB
		"10001451172209c": {"n300", 24 * 1024}, // 12GB (n300 L) + 12GB (n300 R) = 24GB
		"100014511722058": {"n300", 24 * 1024}, // 12GB (n300 L) + 12GB (n300 R) = 24GB
	}

	for boardID, expected := range expectedGpus {
		gpu, exists := gpusByID[boardID]
		if !exists {
			t.Errorf("Expected GPU with board_id %s not found", boardID)
			continue
		}
		if gpu.Name != expected.name {
			t.Errorf("GPU %s: name = %s, want %s", boardID, gpu.Name, expected.name)
		}
		if gpu.Vram != expected.vram {
			t.Errorf("GPU %s: VRAM = %d, want %d", boardID, gpu.Vram, expected.vram)
		}
		if gpu.Vendor != common.GpuVendorTenstorrent {
			t.Errorf("GPU %s: vendor = %v, want %v", boardID, gpu.Vendor, common.GpuVendorTenstorrent)
		}
	}
}

func TestGetGpusFromTtSmiSnapshotGalaxy(t *testing.T) {
	data, err := loadTestData("tenstorrent/galaxy.json")
	if err != nil {
		t.Fatalf("Failed to load test data: %v", err)
	}
	snapshot, err := unmarshalTtSmiSnapshot(data)
	if err != nil {
		t.Fatalf("Failed to unmarshal snapshot: %v", err)
	}

	gpus := getGpusFromTtSmiSnapshot(snapshot)

	// Galaxy.json contains 32 devices with board_type "tt-galaxy-wh L"
	// Each "L" device should be treated as a separate GPU
	// Each "tt-galaxy-wh" device has 12GB VRAM
	if len(gpus) != 32 {
		t.Errorf("getGpusFromTtSmiSnapshot() returned %d GPUs, want 32", len(gpus))
	}

	// Calculate total VRAM: 32 devices × 12GB = 384GB
	totalVram := 32 * 12 * 1024 // 32 devices × 12GB × 1024 MiB/GB
	actualTotalVram := 0

	// Verify all GPUs have the correct properties
	for i, gpu := range gpus {
		if gpu.Vendor != common.GpuVendorTenstorrent {
			t.Errorf("GPU[%d] vendor = %v, want %v", i, gpu.Vendor, common.GpuVendorTenstorrent)
		}
		if gpu.Name != "tt-galaxy-wh" {
			t.Errorf("GPU[%d] name = %s, want tt-galaxy-wh", i, gpu.Name)
		}
		if gpu.ID != "100035100000000" {
			t.Errorf("GPU[%d] ID = %s, want 100035100000000", i, gpu.ID)
		}
		if gpu.Vram != 12*1024 {
			t.Errorf("GPU[%d] VRAM = %d, want %d", i, gpu.Vram, 12*1024)
		}
		// Verify indices are sequential (0, 1, 2, ..., 31)
		expectedIndex := strconv.Itoa(i)
		if gpu.Index != expectedIndex {
			t.Errorf("GPU[%d] index = %s, want %s", i, gpu.Index, expectedIndex)
		}
		actualTotalVram += gpu.Vram
	}

	// Verify total VRAM is 384GB
	if actualTotalVram != totalVram {
		t.Errorf("Total VRAM = %d MiB, want %d MiB (384GB)", actualTotalVram, totalVram)
	}
}
