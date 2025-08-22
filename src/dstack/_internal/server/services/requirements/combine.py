from typing import Callable, Optional, Protocol, TypeVar

from pydantic import BaseModel
from typing_extensions import Self

from dstack._internal.core.models.profiles import Profile, SpotPolicy
from dstack._internal.core.models.resources import (
    CPUSpec,
    DiskSpec,
    GPUSpec,
    Memory,
    Range,
    ResourcesSpec,
)
from dstack._internal.core.models.runs import Requirements
from dstack._internal.utils.typing import SupportsRichComparison


class CombineError(ValueError):
    pass


def combine_fleet_and_run_profiles(
    fleet_profile: Profile, run_profile: Profile
) -> Optional[Profile]:
    """
    Combines fleet and run profile parameters that affect offer selection or provisioning.
    """
    try:
        return Profile(
            backends=_intersect_lists_optional(fleet_profile.backends, run_profile.backends),
            regions=_intersect_lists_optional(fleet_profile.regions, run_profile.regions),
            availability_zones=_intersect_lists_optional(
                fleet_profile.availability_zones, run_profile.availability_zones
            ),
            instance_types=_intersect_lists_optional(
                fleet_profile.instance_types, run_profile.instance_types
            ),
            reservation=_get_single_value_optional(
                fleet_profile.reservation, run_profile.reservation
            ),
            spot_policy=_combine_spot_policy_optional(
                fleet_profile.spot_policy, run_profile.spot_policy
            ),
            max_price=_get_min_optional(fleet_profile.max_price, run_profile.max_price),
            idle_duration=_combine_idle_duration_optional(
                fleet_profile.idle_duration, run_profile.idle_duration
            ),
            tags=_combine_tags_optional(fleet_profile.tags, run_profile.tags),
        )
    except CombineError:
        return None


def combine_fleet_and_run_requirements(
    fleet_requirements: Requirements, run_requirements: Requirements
) -> Optional[Requirements]:
    try:
        return Requirements(
            resources=_combine_resources(fleet_requirements.resources, run_requirements.resources),
            max_price=_get_min_optional(fleet_requirements.max_price, run_requirements.max_price),
            spot=_combine_spot_optional(fleet_requirements.spot, run_requirements.spot),
            reservation=_get_single_value_optional(
                fleet_requirements.reservation, run_requirements.reservation
            ),
        )
    except CombineError:
        return None


_T = TypeVar("_T")
_ModelT = TypeVar("_ModelT", bound=BaseModel)
_CompT = TypeVar("_CompT", bound=SupportsRichComparison)


class _SupportsCopy(Protocol):
    def copy(self) -> Self: ...


_CopyT = TypeVar("_CopyT", bound=_SupportsCopy)


def _intersect_lists_optional(
    list1: Optional[list[_T]], list2: Optional[list[_T]]
) -> Optional[list[_T]]:
    if list1 is None:
        if list2 is None:
            return None
        return list2.copy()
    if list2 is None:
        return list1.copy()
    return [x for x in list1 if x in list2]


def _get_min(value1: _CompT, value2: _CompT) -> _CompT:
    return min(value1, value2)


def _get_min_optional(value1: Optional[_CompT], value2: Optional[_CompT]) -> Optional[_CompT]:
    return _combine_optional(value1, value2, _get_min)


def _get_single_value(value1: _T, value2: _T) -> _T:
    if value1 == value2:
        return value1
    raise CombineError(f"Values {value1} and {value2} cannot be combined")


def _get_single_value_optional(value1: Optional[_T], value2: Optional[_T]) -> Optional[_T]:
    return _combine_optional(value1, value2, _get_single_value)


def _combine_spot_policy(value1: SpotPolicy, value2: SpotPolicy) -> SpotPolicy:
    if value1 == SpotPolicy.AUTO:
        return value2
    if value2 == SpotPolicy.AUTO:
        return value1
    if value1 == value2:
        return value1
    raise CombineError(f"spot_policy values {value1} and {value2} cannot be combined")


def _combine_spot_policy_optional(
    value1: Optional[SpotPolicy], value2: Optional[SpotPolicy]
) -> Optional[SpotPolicy]:
    return _combine_optional(value1, value2, _combine_spot_policy)


def _combine_idle_duration(value1: int, value2: int) -> int:
    if value1 < 0 and value2 >= 0 or value2 < 0 and value1 >= 0:
        raise CombineError(f"idle_duration values {value1} and {value2} cannot be combined")
    return min(value1, value2)


def _combine_idle_duration_optional(value1: Optional[int], value2: Optional[int]) -> Optional[int]:
    return _combine_optional(value1, value2, _combine_idle_duration)


def _combine_tags_optional(
    value1: Optional[dict[str, str]], value2: Optional[dict[str, str]]
) -> Optional[dict[str, str]]:
    return _combine_copy_optional(value1, value2, _combine_tags)


def _combine_tags(value1: dict[str, str], value2: dict[str, str]) -> dict[str, str]:
    return value1 | value2


def _combine_resources(value1: ResourcesSpec, value2: ResourcesSpec) -> ResourcesSpec:
    return ResourcesSpec(
        cpu=_combine_cpu(value1.cpu, value2.cpu),  # type: ignore[attr-defined]
        memory=_combine_memory(value1.memory, value2.memory),
        shm_size=_combine_shm_size_optional(value1.shm_size, value2.shm_size),
        gpu=_combine_gpu_optional(value1.gpu, value2.gpu),
        disk=_combine_disk_optional(value1.disk, value2.disk),
    )


def _combine_cpu(value1: CPUSpec, value2: CPUSpec) -> CPUSpec:
    return CPUSpec(
        arch=_get_single_value_optional(value1.arch, value2.arch),
        count=_combine_range(value1.count, value2.count),
    )


def _combine_memory(value1: Range[Memory], value2: Range[Memory]) -> Range[Memory]:
    return _combine_range(value1, value2)


def _combine_shm_size_optional(
    value1: Optional[Memory], value2: Optional[Memory]
) -> Optional[Memory]:
    return _get_min_optional(value1, value2)


def _combine_gpu(value1: GPUSpec, value2: GPUSpec) -> GPUSpec:
    return GPUSpec(
        vendor=_get_single_value_optional(value1.vendor, value2.vendor),
        name=_intersect_lists_optional(value1.name, value2.name),
        count=_combine_range(value1.count, value2.count),
        memory=_combine_range_optional(value1.memory, value2.memory),
        total_memory=_combine_range_optional(value1.total_memory, value2.total_memory),
        compute_capability=_get_min_optional(value1.compute_capability, value2.compute_capability),
    )


def _combine_gpu_optional(
    value1: Optional[GPUSpec], value2: Optional[GPUSpec]
) -> Optional[GPUSpec]:
    return _combine_models_optional(value1, value2, _combine_gpu)


def _combine_disk(value1: DiskSpec, value2: DiskSpec) -> DiskSpec:
    return DiskSpec(size=_combine_range(value1.size, value2.size))


def _combine_disk_optional(
    value1: Optional[DiskSpec], value2: Optional[DiskSpec]
) -> Optional[DiskSpec]:
    return _combine_models_optional(value1, value2, _combine_disk)


def _combine_spot(value1: bool, value2: bool) -> bool:
    if value1 != value2:
        raise CombineError(f"spot values {value1} and {value2} cannot be combined")
    return value1


def _combine_spot_optional(value1: Optional[bool], value2: Optional[bool]) -> Optional[bool]:
    return _combine_optional(value1, value2, _combine_spot)


def _combine_range(value1: Range, value2: Range) -> Range:
    res = value1.intersect(value2)
    if res is None:
        raise CombineError(f"Ranges {value1} and {value2} cannot be combined")
    return res


def _combine_range_optional(value1: Optional[Range], value2: Optional[Range]) -> Optional[Range]:
    return _combine_models_optional(value1, value2, _combine_range)


def _combine_optional(
    value1: Optional[_T], value2: Optional[_T], combiner: Callable[[_T, _T], _T]
) -> Optional[_T]:
    if value1 is None:
        return value2
    if value2 is None:
        return value1
    return combiner(value1, value2)


def _combine_models_optional(
    value1: Optional[_ModelT],
    value2: Optional[_ModelT],
    combiner: Callable[[_ModelT, _ModelT], _ModelT],
) -> Optional[_ModelT]:
    if value1 is None:
        if value2 is not None:
            return value2.copy(deep=True)
        return None
    if value2 is None:
        return value1.copy(deep=True)
    return combiner(value1, value2)


def _combine_copy_optional(
    value1: Optional[_CopyT],
    value2: Optional[_CopyT],
    combiner: Callable[[_CopyT, _CopyT], _CopyT],
) -> Optional[_CopyT]:
    if value1 is None:
        if value2 is not None:
            return value2.copy()
        return None
    if value2 is None:
        return value1.copy()
    return combiner(value1, value2)
