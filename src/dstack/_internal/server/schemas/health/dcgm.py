from enum import IntEnum

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.health import HealthStatus


class DCGMHealthResult(IntEnum):
    """
    `dcgmHealthWatchResult_enum`

    See: https://github.com/NVIDIA/go-dcgm/blob/85ceb31/pkg/dcgm/const.go#L1020-L1026
    """

    DCGM_HEALTH_RESULT_PASS = 0
    DCGM_HEALTH_RESULT_WARN = 10
    DCGM_HEALTH_RESULT_FAIL = 20

    def to_health_status(self) -> HealthStatus:
        if self == self.DCGM_HEALTH_RESULT_PASS:
            return HealthStatus.HEALTHY
        if self == self.DCGM_HEALTH_RESULT_WARN:
            return HealthStatus.WARNING
        if self == self.DCGM_HEALTH_RESULT_FAIL:
            return HealthStatus.FAILURE
        raise AssertionError("should not reach here")


class DCGMHealthIncident(CoreModel):
    """
    Flattened `dcgmIncidentInfo_t`

    See: https://github.com/NVIDIA/go-dcgm/blob/85ceb31/pkg/dcgm/health.go#L68-L73
    """

    # dcgmIncidentInfo_t
    system: int
    health: DCGMHealthResult

    # dcgmDiagErrorDetail_t
    error_message: str
    error_code: int

    # dcgmGroupEntityPair_t
    entity_group_id: int  # dcgmGroupEntityPair_t
    entity_id: int


class DCGMHealthResponse(CoreModel):
    """
    `dcgmHealthResponse_v5`

    See: https://github.com/NVIDIA/go-dcgm/blob/85ceb31/pkg/dcgm/health.go#L75-L78
    """

    overall_health: DCGMHealthResult
    incidents: list[DCGMHealthIncident]
