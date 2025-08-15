//go:build linux

package dcgm

import (
	"strings"
	"testing"
	"time"

	godcgm "github.com/NVIDIA/go-dcgm/pkg/dcgm"
	"github.com/stretchr/testify/require"
)

func TestDCGMWrapperGetHealth(t *testing.T) {
	dcgmw := getDCGMWrapper(t)
	defer dcgmw.Shutdown()

	gpuID := getGpuID(t)

	err := dcgmw.EnableHealthChecks()
	require.NoError(t, err)

	health, err := dcgmw.GetHealth()
	require.NoError(t, err)
	require.Equal(t, health.OverallHealth, 0) // DCGM_HEALTH_RESULT_PASS
	require.Len(t, health.Incidents, 0)

	injectError(t, gpuID, godcgm.DCGM_FI_DEV_ECC_DBE_VOL_TOTAL, godcgm.DCGM_FT_INT64, int64(888))
	injectError(t, gpuID, godcgm.DCGM_FI_DEV_PCIE_REPLAY_COUNTER, godcgm.DCGM_FT_INT64, int64(999))

	health, err = dcgmw.GetHealth()
	require.NoError(t, err)
	require.Equal(t, health.OverallHealth, 20) // DCGM_HEALTH_RESULT_FAIL
	require.Len(t, health.Incidents, 2)
	for _, incident := range health.Incidents {
		switch incident.System {
		case 0x1: // DCGM_HEALTH_WATCH_PCIE
			require.Equal(t, incident.Health, 10) // DCGM_HEALTH_RESULT_WARN
			require.Contains(t, incident.ErrorMessage, "PCIe replay")
		case 0x10: // DCGM_HEALTH_WATCH_MEM
			require.Equal(t, incident.Health, 20) // DCGM_HEALTH_RESULT_FAIL
			require.Contains(t, incident.ErrorMessage, "volatile double-bit ECC error")
		default:
			t.Logf("unexpected HealthSystem: 0x%x", incident.System)
			t.FailNow()
		}
		require.Equal(t, incident.EntityGroupID, 1) // FE_GPU
		require.Equal(t, incident.EntityID, int(gpuID))
	}
}

// Utils. Must be called after NewDCGMWrapper(), as it indirectly calls dlopen("libdcgm.so.4")

func getDCGMWrapper(t *testing.T) *DCGMWrapper {
	dcgmw, err := NewDCGMWrapper("")
	if err != nil && strings.Contains(err.Error(), "libdcgm.so") {
		t.Skip("Skipping test that requires ligdcm.so")
	}
	require.NoError(t, err)
	gpuIDs, err := godcgm.GetSupportedDevices()
	require.NoError(t, err)
	if len(gpuIDs) < 1 {
		t.Skip("Skipping test that requires live GPUs. None were found")
	}
	return dcgmw
}

func getGpuID(t *testing.T) uint {
	t.Helper()
	gpuIDs, err := godcgm.GetSupportedDevices()
	require.NoError(t, err)
	if len(gpuIDs) < 1 {
		t.Skip("Skipping test that requires live GPUs. None were found")
	}
	return gpuIDs[0]
}

func injectError(t *testing.T, gpuID uint, fieldID godcgm.Short, fieldType uint, value any) {
	t.Helper()
	err := godcgm.InjectFieldValue(gpuID, fieldID, fieldType, 0, time.Now().UnixMicro(), value)
	require.NoError(t, err)
}
