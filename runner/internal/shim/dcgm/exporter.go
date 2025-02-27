package dcgm

import (
	"context"
	"encoding/csv"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/alexellis/go-execute/v2"
	"github.com/dstackai/dstack/runner/internal/log"
)

// Counter represents a single line in counters.csv, see
// https://github.com/NVIDIA/dcgm-exporter/tree/5f9250c211?tab=readme-ov-file#changing-metrics
// For list of supported types see
// https://github.com/NVIDIA/dcgm-exporter/blob/5f9250c211/internal/pkg/counters/variables.go#L23
// NB: Although it is called "counter" in dcgm-exporter, in fact it can be any Prometheus
// metric type or even a label
type Counter struct {
	Name string
	Type string
	Help string
}

// Full list: https://docs.nvidia.com/datacenter/dcgm/latest/dcgm-api/dcgm-api-field-ids.html
var counters = [...]Counter{
	{"DCGM_FI_DEV_GPU_UTIL", "gauge", "GPU utilization (in %)."},
	{"DCGM_FI_DEV_MEM_COPY_UTIL", "gauge", "Memory utilization (in %)."},
	{"DCGM_FI_DEV_ENC_UTIL", "gauge", "Encoder utilization (in %)."},
	{"DCGM_FI_DEV_DEC_UTIL", "gauge", "Decoder utilization (in %)."},
	{"DCGM_FI_DEV_FB_FREE", "gauge", "Framebuffer memory free (in MiB)."},
	{"DCGM_FI_DEV_FB_USED", "gauge", "Framebuffer memory used (in MiB)."},
	{"DCGM_FI_PROF_GR_ENGINE_ACTIVE", "gauge", "The ratio of cycles during which a graphics engine or compute engine remains active."},
	{"DCGM_FI_PROF_SM_ACTIVE", "gauge", "The ratio of cycles an SM has at least 1 warp assigned."},
	{"DCGM_FI_PROF_SM_OCCUPANCY", "gauge", "The ratio of number of warps resident on an SM."},
	{"DCGM_FI_PROF_PIPE_TENSOR_ACTIVE", "gauge", "Ratio of cycles the tensor (HMMA) pipe is active."},
	{"DCGM_FI_PROF_PIPE_FP64_ACTIVE", "gauge", "Ratio of cycles the fp64 pipes are active."},
	{"DCGM_FI_PROF_PIPE_FP32_ACTIVE", "gauge", "Ratio of cycles the fp32 pipes are active."},
	{"DCGM_FI_PROF_PIPE_FP16_ACTIVE", "gauge", "Ratio of cycles the fp16 pipes are active."},
	{"DCGM_FI_PROF_PIPE_INT_ACTIVE", "gauge", "Ratio of cycles the integer pipe is active."},
	{"DCGM_FI_PROF_DRAM_ACTIVE", "gauge", "Ratio of cycles the device memory interface is active sending or receiving data."},
	{"DCGM_FI_PROF_PCIE_TX_BYTES", "counter", "The number of bytes of active PCIe tx (transmit) data including both header and payload."},
	{"DCGM_FI_PROF_PCIE_RX_BYTES", "counter", "The number of bytes of active PCIe rx (read) data including both header and payload."},
	{"DCGM_FI_DEV_SM_CLOCK", "gauge", "SM clock frequency (in MHz)."},
	{"DCGM_FI_DEV_MEM_CLOCK", "gauge", "Memory clock frequency (in MHz)."},
	{"DCGM_FI_DEV_MEMORY_TEMP", "gauge", "Memory temperature (in C)."},
	{"DCGM_FI_DEV_GPU_TEMP", "gauge", "GPU temperature (in C)."},
	{"DCGM_FI_DEV_POWER_USAGE", "gauge", "Power draw (in W)."},
	{"DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION", "counter", "Total energy consumption since boot (in mJ)."},
	{"DCGM_FI_DEV_PCIE_REPLAY_COUNTER", "counter", "Total number of PCIe retries."},
	{"DCGM_FI_DEV_XID_ERRORS", "gauge", "Value of the last XID error encountered."},
	{"DCGM_FI_DEV_POWER_VIOLATION", "counter", "Throttling duration due to power constraints (in us)."},
	{"DCGM_FI_DEV_THERMAL_VIOLATION", "counter", "Throttling duration due to thermal constraints (in us)."},
	{"DCGM_FI_DEV_SYNC_BOOST_VIOLATION", "counter", "Throttling duration due to sync-boost constraints (in us)."},
	{"DCGM_FI_DEV_BOARD_LIMIT_VIOLATION", "counter", "Throttling duration due to board limit constraints (in us)."},
	{"DCGM_FI_DEV_LOW_UTIL_VIOLATION", "counter", "Throttling duration due to low utilization (in us)."},
	{"DCGM_FI_DEV_RELIABILITY_VIOLATION", "counter", "Throttling duration due to reliability constraints (in us)."},
	{"DCGM_FI_DEV_ECC_SBE_VOL_TOTAL", "counter", "Total number of single-bit volatile ECC errors."},
	{"DCGM_FI_DEV_ECC_DBE_VOL_TOTAL", "counter", "Total number of double-bit volatile ECC errors."},
	{"DCGM_FI_DEV_ECC_SBE_AGG_TOTAL", "counter", "Total number of single-bit persistent ECC errors."},
	{"DCGM_FI_DEV_ECC_DBE_AGG_TOTAL", "counter", "Total number of double-bit persistent ECC errors."},
	{"DCGM_FI_DEV_RETIRED_SBE", "counter", "Total number of retired pages due to single-bit errors."},
	{"DCGM_FI_DEV_RETIRED_DBE", "counter", "Total number of retired pages due to double-bit errors."},
	{"DCGM_FI_DEV_RETIRED_PENDING", "counter", "Total number of pages pending retirement."},
	{"DCGM_FI_DEV_UNCORRECTABLE_REMAPPED_ROWS", "counter", "Number of remapped rows for uncorrectable errors"},
	{"DCGM_FI_DEV_CORRECTABLE_REMAPPED_ROWS", "counter", "Number of remapped rows for correctable errors"},
	{"DCGM_FI_DEV_ROW_REMAP_FAILURE", "gauge", "Whether remapping of rows has failed"},
	{"DCGM_FI_DEV_NVLINK_CRC_FLIT_ERROR_COUNT_TOTAL", "counter", "Total number of NVLink flow-control CRC errors."},
	{"DCGM_FI_DEV_NVLINK_CRC_DATA_ERROR_COUNT_TOTAL", "counter", "Total number of NVLink data CRC errors."},
	{"DCGM_FI_DEV_NVLINK_REPLAY_ERROR_COUNT_TOTAL", "counter", "Total number of NVLink retries."},
	{"DCGM_FI_DEV_NVLINK_RECOVERY_ERROR_COUNT_TOTAL", "counter", "Total number of NVLink recovery errors."},
	{"DCGM_FI_DEV_NVLINK_BANDWIDTH_TOTAL", "counter", "Total number of NVLink bandwidth counters for all lanes."},
	{"DCGM_FI_DEV_NVLINK_BANDWIDTH_L0", "counter", "The number of bytes of active NVLink rx or tx data including both header and payload."},
	{"DCGM_FI_PROF_NVLINK_RX_BYTES", "counter", "The number of bytes of active PCIe rx (read) data including both header and payload. "},
	{"DCGM_FI_PROF_NVLINK_TX_BYTES", "counter", "The number of bytes of active NvLink tx (transmit) data including both header and payload. "},
}

const dcgmExporterExecName = "dcgm-exporter"

type DCGMExporter struct {
	cmd           *exec.Cmd
	cancel        context.CancelFunc
	execPath      string
	listenAddr    string
	client        *http.Client
	url           string
	interval      time.Duration
	configPath    string
	mu            sync.Mutex
	lastFetchedAt time.Time
	lastResponse  []byte
}

func (c *DCGMExporter) Start(ctx context.Context) error {
	if c.cmd != nil {
		return errors.New("already started")
	}

	configFile, err := os.CreateTemp("", "counters-*.csv")
	if err != nil {
		return err
	}
	defer configFile.Close()
	c.configPath = configFile.Name()
	configWriter := csv.NewWriter(configFile)
	for _, counter := range counters {
		err := configWriter.Write([]string{counter.Name, counter.Type, counter.Help})
		if err != nil {
			return err
		}
	}
	configWriter.Flush()

	cmdCtx, cmdCancel := context.WithCancel(ctx)
	c.cancel = cmdCancel
	cmd := exec.CommandContext(
		cmdCtx, c.execPath,
		"-f", c.configPath,
		"-a", c.listenAddr,
		"-c", strconv.Itoa(int(c.interval.Milliseconds())),
	)
	c.cmd = cmd
	cmd.Cancel = func() error {
		return cmd.Process.Signal(syscall.SIGTERM)
	}
	cmd.WaitDelay = 5 * time.Second
	return cmd.Start()
}

func (c *DCGMExporter) Stop(context.Context) error {
	if c.cmd == nil {
		return errors.New("not started")
	}
	c.cancel()
	os.Remove(c.configPath)
	return c.cmd.Wait()
}

func (c *DCGMExporter) Fetch(ctx context.Context) ([]byte, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	now := time.Now()

	if now.Sub(c.lastFetchedAt) < c.interval {
		return c.lastResponse, nil
	}

	req, err := http.NewRequestWithContext(ctx, "GET", c.url, nil)
	if err != nil {
		return nil, err
	}
	resp, err := c.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("status is not OK: %d", resp.StatusCode)
	}
	response, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	c.lastFetchedAt = now
	c.lastResponse = response
	return response, nil
}

func NewDCGMExporter(execPath string, port int, interval time.Duration) *DCGMExporter {
	listenAddr := fmt.Sprintf("localhost:%d", port)
	client := &http.Client{
		Timeout: 10 * time.Second,
	}
	return &DCGMExporter{
		execPath:   execPath,
		listenAddr: listenAddr,
		client:     client,
		url:        fmt.Sprintf("http://%s/metrics", listenAddr),
		interval:   interval,
	}
}

func GetDCGMExporterExecPath(ctx context.Context) (string, error) {
	path, err := exec.LookPath(dcgmExporterExecName)
	if err != nil {
		return "", err
	}
	cmd := execute.ExecTask{
		Command:     path,
		Args:        []string{"-v"},
		StreamStdio: false,
	}
	res, err := cmd.Execute(ctx)
	if err != nil {
		return "", err
	}
	if res.ExitCode != 0 {
		return "", fmt.Errorf("%s returned %d, stderr: %s, stdout: %s", path, res.ExitCode, res.Stderr, res.Stdout)
	}
	log.Debug(ctx, "detected", "path", path, "version", strings.TrimSpace(res.Stdout))
	return path, nil
}
