package host

import (
	"os"
	"path/filepath"
	"reflect"
	"strconv"
	"testing"

	"github.com/dstackai/dstack/runner/internal/common/gpu"
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
			Vendor: gpu.GpuVendorTenstorrent,
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
		gpu_, exists := gpusByID[boardID]
		if !exists {
			t.Errorf("Expected GPU with board_id %s not found", boardID)
			continue
		}
		if gpu_.Name != expected.name {
			t.Errorf("GPU %s: name = %s, want %s", boardID, gpu_.Name, expected.name)
		}
		if gpu_.Vram != expected.vram {
			t.Errorf("GPU %s: VRAM = %d, want %d", boardID, gpu_.Vram, expected.vram)
		}
		if gpu_.Vendor != gpu.GpuVendorTenstorrent {
			t.Errorf("GPU %s: vendor = %v, want %v", boardID, gpu_.Vendor, gpu.GpuVendorTenstorrent)
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
	for i, gpu_ := range gpus {
		if gpu_.Vendor != gpu.GpuVendorTenstorrent {
			t.Errorf("GPU[%d] vendor = %v, want %v", i, gpu_.Vendor, gpu.GpuVendorTenstorrent)
		}
		if gpu_.Name != "tt-galaxy-wh" {
			t.Errorf("GPU[%d] name = %s, want tt-galaxy-wh", i, gpu_.Name)
		}
		if gpu_.ID != "100035100000000" {
			t.Errorf("GPU[%d] ID = %s, want 100035100000000", i, gpu_.ID)
		}
		if gpu_.Vram != 12*1024 {
			t.Errorf("GPU[%d] VRAM = %d, want %d", i, gpu_.Vram, 12*1024)
		}
		// Verify indices are sequential (0, 1, 2, ..., 31)
		expectedIndex := strconv.Itoa(i)
		if gpu_.Index != expectedIndex {
			t.Errorf("GPU[%d] index = %s, want %s", i, gpu_.Index, expectedIndex)
		}
		actualTotalVram += gpu_.Vram
	}

	// Verify total VRAM is 384GB
	if actualTotalVram != totalVram {
		t.Errorf("Total VRAM = %d MiB, want %d MiB (384GB)", actualTotalVram, totalVram)
	}
}

func TestGetGpusFromTtSmiSnapshotBlackholeRevisions(t *testing.T) {
	snapshot := &ttSmiSnapshot{
		DeviceInfo: []ttDeviceInfo{
			{BoardInfo: ttBoardInfo{BoardType: "bh-scrappy", BoardID: "0000360000000000"}},
			{BoardInfo: ttBoardInfo{BoardType: "p100", BoardID: "0000430000000000"}},
			{BoardInfo: ttBoardInfo{BoardType: "p100a", BoardID: "0000430000000000"}},
			{BoardInfo: ttBoardInfo{BoardType: "p150a", BoardID: "0000400000000000"}},
			{BoardInfo: ttBoardInfo{BoardType: "p150b", BoardID: "0000410000000000"}},
			{BoardInfo: ttBoardInfo{BoardType: "p150c", BoardID: "0000420000000000"}},
			{BoardInfo: ttBoardInfo{BoardType: "p300b", BoardID: "0000440000000000"}},
			{BoardInfo: ttBoardInfo{BoardType: "p300a", BoardID: "0000450000000000"}},
			{BoardInfo: ttBoardInfo{BoardType: "p300c", BoardID: "0000460000000000"}},
		},
	}

	gpus := getGpusFromTtSmiSnapshot(snapshot)

	expectedNames := []string{"p100a", "p100a", "p100a", "p150", "p150", "p150", "p300", "p300", "p300"}
	expectedVram := []int{28 * 1024, 28 * 1024, 28 * 1024, 32 * 1024, 32 * 1024, 32 * 1024, 32 * 1024, 32 * 1024, 32 * 1024}
	if len(gpus) != len(expectedNames) {
		t.Fatalf("getGpusFromTtSmiSnapshot() returned %d GPUs, want %d", len(gpus), len(expectedNames))
	}
	for i, expectedName := range expectedNames {
		if gpus[i].Vendor != gpu.GpuVendorTenstorrent {
			t.Errorf("GPU[%d] vendor = %v, want %v", i, gpus[i].Vendor, gpu.GpuVendorTenstorrent)
		}
		if gpus[i].Name != expectedName {
			t.Errorf("GPU[%d] name = %s, want %s", i, gpus[i].Name, expectedName)
		}
		if gpus[i].Vram != expectedVram[i] {
			t.Errorf("GPU[%d] VRAM = %d, want %d", i, gpus[i].Vram, expectedVram[i])
		}
		if gpus[i].Index != strconv.Itoa(i) {
			t.Errorf("GPU[%d] index = %s, want %s", i, gpus[i].Index, strconv.Itoa(i))
		}
	}
}

func TestGetGpusFromTtSmiSnapshotBlackholeSourceFixtures(t *testing.T) {
	// Derived from TT-Metal UMD Blackhole board descriptors.
	data, err := loadTestData("tenstorrent/blackhole_boards.json")
	if err != nil {
		t.Fatalf("Failed to load test data: %v", err)
	}
	snapshot, err := unmarshalTtSmiSnapshot(data)
	if err != nil {
		t.Fatalf("Failed to unmarshal snapshot: %v", err)
	}

	gpus := getGpusFromTtSmiSnapshot(snapshot)

	expected := []GpuInfo{
		{Vendor: gpu.GpuVendorTenstorrent, Name: "p100a", Vram: 28 * 1024, ID: "000004323191b040", Index: "0"},
		{Vendor: gpu.GpuVendorTenstorrent, Name: "p150", Vram: 32 * 1024, ID: "0000040100000000", Index: "1"},
		{Vendor: gpu.GpuVendorTenstorrent, Name: "p150", Vram: 32 * 1024, ID: "000004123191110e", Index: "2"},
		{Vendor: gpu.GpuVendorTenstorrent, Name: "p300", Vram: 32 * 1024, ID: "000004513190f004", Index: "3"},
		{Vendor: gpu.GpuVendorTenstorrent, Name: "p300", Vram: 32 * 1024, ID: "000004513190f004", Index: "4"},
	}
	if !reflect.DeepEqual(gpus, expected) {
		t.Errorf("getGpusFromTtSmiSnapshot() = %v, want %v", gpus, expected)
	}
}

func TestGetGpusFromTtSmiSnapshotBlackholeEightP150(t *testing.T) {
	// Derived from TT-Metal UMD blackhole_8xP150 cluster descriptor.
	data, err := loadTestData("tenstorrent/blackhole_8xp150.json")
	if err != nil {
		t.Fatalf("Failed to load test data: %v", err)
	}
	snapshot, err := unmarshalTtSmiSnapshot(data)
	if err != nil {
		t.Fatalf("Failed to unmarshal snapshot: %v", err)
	}

	gpus := getGpusFromTtSmiSnapshot(snapshot)

	expectedIDs := []string{
		"0000041231915018",
		"0000041231915002",
		"0000041231915009",
		"000004123191500f",
		"0000041231914064",
		"0000041231915006",
		"0000041231914087",
		"000004123191402f",
	}
	if len(gpus) != len(expectedIDs) {
		t.Fatalf("getGpusFromTtSmiSnapshot() returned %d GPUs, want %d", len(gpus), len(expectedIDs))
	}
	for i, gpu_ := range gpus {
		if gpu_.Vendor != gpu.GpuVendorTenstorrent {
			t.Errorf("GPU[%d] vendor = %v, want %v", i, gpu_.Vendor, gpu.GpuVendorTenstorrent)
		}
		if gpu_.Name != "p150" {
			t.Errorf("GPU[%d] name = %s, want p150", i, gpu_.Name)
		}
		if gpu_.Vram != 32*1024 {
			t.Errorf("GPU[%d] VRAM = %d, want %d", i, gpu_.Vram, 32*1024)
		}
		if gpu_.ID != expectedIDs[i] {
			t.Errorf("GPU[%d] ID = %s, want %s", i, gpu_.ID, expectedIDs[i])
		}
		if gpu_.Index != strconv.Itoa(i) {
			t.Errorf("GPU[%d] index = %s, want %s", i, gpu_.Index, strconv.Itoa(i))
		}
	}
}

func TestGetGpusFromTtSmiSnapshotBlackholeP300SameBoardID(t *testing.T) {
	snapshot := &ttSmiSnapshot{
		DeviceInfo: []ttDeviceInfo{
			{BoardInfo: ttBoardInfo{BoardType: "p300a", BoardID: "0000450000000000", BusID: "0000:01:00.0"}},
			{BoardInfo: ttBoardInfo{BoardType: "p300a", BoardID: "0000450000000000", BusID: "0000:02:00.0"}},
		},
	}

	gpus := getGpusFromTtSmiSnapshot(snapshot)

	if len(gpus) != 2 {
		t.Fatalf("getGpusFromTtSmiSnapshot() returned %d GPUs, want 2", len(gpus))
	}
	for i, gpu_ := range gpus {
		if gpu_.Name != "p300" {
			t.Errorf("GPU[%d] name = %s, want p300", i, gpu_.Name)
		}
		if gpu_.Vram != 32*1024 {
			t.Errorf("GPU[%d] VRAM = %d, want %d", i, gpu_.Vram, 32*1024)
		}
		if gpu_.Index != strconv.Itoa(i) {
			t.Errorf("GPU[%d] index = %s, want %s", i, gpu_.Index, strconv.Itoa(i))
		}
	}
}

func TestGetGpusFromTtSmiSnapshotBlackholeP300RemoteChip(t *testing.T) {
	snapshot := &ttSmiSnapshot{
		DeviceInfo: []ttDeviceInfo{
			{BoardInfo: ttBoardInfo{BoardType: "p300a", BoardID: "0000450000000000", BusID: "0000:01:00.0"}},
			{BoardInfo: ttBoardInfo{BoardType: "p300a", BoardID: "0000450000000000", BusID: "N/A"}},
		},
	}

	gpus := getGpusFromTtSmiSnapshot(snapshot)

	expected := []GpuInfo{
		{Vendor: gpu.GpuVendorTenstorrent, Name: "p300", Vram: 64 * 1024, ID: "0000450000000000", Index: "0"},
	}
	if !reflect.DeepEqual(gpus, expected) {
		t.Errorf("getGpusFromTtSmiSnapshot() = %v, want %v", gpus, expected)
	}
}

func TestGetGpusFromTtSmiSnapshotBlackholeGalaxy(t *testing.T) {
	data, err := loadTestData("tenstorrent/blackhole_galaxy.json")
	if err != nil {
		t.Fatalf("Failed to load test data: %v", err)
	}
	snapshot, err := unmarshalTtSmiSnapshot(data)
	if err != nil {
		t.Fatalf("Failed to unmarshal snapshot: %v", err)
	}

	gpus := getGpusFromTtSmiSnapshot(snapshot)

	if len(gpus) != 32 {
		t.Fatalf("getGpusFromTtSmiSnapshot() returned %d GPUs, want 32", len(gpus))
	}
	for i, gpu_ := range gpus {
		if gpu_.Name != "tt-galaxy-bh" {
			t.Errorf("GPU[%d] name = %s, want tt-galaxy-bh", i, gpu_.Name)
		}
		if gpu_.Vram != 32*1024 {
			t.Errorf("GPU[%d] VRAM = %d, want %d", i, gpu_.Vram, 32*1024)
		}
		if gpu_.Index != strconv.Itoa(i) {
			t.Errorf("GPU[%d] index = %s, want %s", i, gpu_.Index, strconv.Itoa(i))
		}
	}
}
