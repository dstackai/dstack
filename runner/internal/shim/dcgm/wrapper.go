package dcgm

type HealthStatus string

const (
	HealthStatusHealthy HealthStatus = "healthy"
	HealthStatusWarning HealthStatus = "warning"
	HealthStatusFailure HealthStatus = "failure"
)

type HealthIncident struct {
	System        int    `json:"system"`
	Health        int    `json:"health"`
	ErrorMessage  string `json:"error_message"`
	ErrorCode     int    `json:"error_code"`
	EntityGroupID int    `json:"entity_group_id"`
	EntityID      int    `json:"entity_id"`
}

type Health struct {
	OverallHealth int              `json:"overall_health"`
	Incidents     []HealthIncident `json:"incidents"`
}

type DCGMWrapperInterface interface {
	Shutdown() error
	EnableHealthChecks() error
	GetHealth() (Health, error)
}
