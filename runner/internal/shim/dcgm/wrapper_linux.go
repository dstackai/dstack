//go:build linux

package dcgm

import (
	"errors"
	"fmt"
	"sync"

	godcgm "github.com/NVIDIA/go-dcgm/pkg/dcgm"
)

// DCGMWrapper is a wrapper around go-dcgm (which, in turn, is a wrapper around libdcgm.so)
type DCGMWrapper struct {
	group              godcgm.GroupHandle
	healthCheckEnabled bool

	mu *sync.Mutex
}

// NewDCGMWrapper initializes and starts DCGM in the specific mode:
//   - If address is empty, then libdcgm starts embedded hostengine within the current process.
//     This is the main mode.
//   - If address is not empty, then libdcgm connects to already running nv-hostengine service via TCP.
//     This mode is useful for debugging, e.g., one can start nv-hostengine via systemd and inject
//     errors via dcgmi:
//   - systemctl start nvidia-dcgm.service
//   - dcgmi test --inject --gpuid 0 -f 202 -v 99999
//
// Note: embedded hostengine is started in AUTO operation mode, which means that
// the library handles periodic tasks by itself executing them in additional threads.
func NewDCGMWrapper(address string) (*DCGMWrapper, error) {
	var err error
	if address == "" {
		_, err = godcgm.Init(godcgm.Embedded)
	} else {
		// "address is a unix socket filename (1) or a TCP/IP address (0)"
		_, err = godcgm.Init(godcgm.Standalone, address, "0")
	}
	if err != nil {
		return nil, fmt.Errorf("failed to initialize or start DCGM: %w", err)
	}
	return &DCGMWrapper{
		group: godcgm.GroupAllGPUs(),
		mu:    new(sync.Mutex),
	}, nil
}

func (w *DCGMWrapper) Shutdown() error {
	if err := godcgm.Shutdown(); err != nil {
		return fmt.Errorf("failed to shut down DCGM: %w", err)
	}
	return nil
}

func (w *DCGMWrapper) EnableHealthChecks() error {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.healthCheckEnabled {
		return errors.New("health check system already enabled")
	}
	if err := godcgm.HealthSet(w.group, godcgm.DCGM_HEALTH_WATCH_ALL); err != nil {
		return fmt.Errorf("failed to configure health watches: %w", err)
	}
	// "On the first call, stateful information about all of the enabled watches within a group
	// is created but no error results are provided. On subsequent calls, any error information
	// will be returned."
	if _, err := godcgm.HealthCheck(w.group); err != nil {
		return fmt.Errorf("failed to initialize health watches state: %w", err)
	}
	w.healthCheckEnabled = true
	return nil
}

func (w *DCGMWrapper) GetHealth() (Health, error) {
	health := Health{}
	if !w.healthCheckEnabled {
		return health, errors.New("health check system is not enabled")
	}
	response, err := godcgm.HealthCheck(w.group)
	if err != nil {
		return health, fmt.Errorf("failed to fetch health status: %w", err)
	}
	health.OverallHealth = int(response.OverallHealth)
	health.Incidents = make([]HealthIncident, 0, len(response.Incidents))
	for _, incident := range response.Incidents {
		health.Incidents = append(health.Incidents, HealthIncident{
			System:        int(incident.System),
			Health:        int(incident.Health),
			ErrorMessage:  incident.Error.Message,
			ErrorCode:     int(incident.Error.Code),
			EntityGroupID: int(incident.EntityInfo.EntityGroupId),
			EntityID:      int(incident.EntityInfo.EntityId),
		})
	}
	return health, nil
}
