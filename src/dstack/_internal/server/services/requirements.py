from typing import Optional, TypeVar, Union

from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.resources import (
    CPUSpec,
    DiskSpec,
    GPUSpec,
    Memory,
    Range,
    ResourcesSpec,
)
from dstack._internal.core.models.runs import Requirements


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
            backends=_intersect_lists(fleet_profile.backends, run_profile.backends),
            regions=_intersect_lists(fleet_profile.regions, run_profile.regions),
            availability_zones=_intersect_lists(
                fleet_profile.availability_zones, run_profile.availability_zones
            ),
            instance_types=_intersect_lists(
                fleet_profile.instance_types, run_profile.instance_types
            ),
            reservation=_get_optional_single_value(
                fleet_profile.reservation, run_profile.reservation
            ),
            max_price=_get_optional_min(fleet_profile.max_price, run_profile.max_price),
            idle_duration=_combine_idle_duration(
                fleet_profile.idle_duration, run_profile.idle_duration
            ),  # converted by validator
        )
    except CombineError:
        return None


def combine_fleet_and_run_requirements(
    fleet_requirements: Requirements, run_requirements: Requirements
) -> Optional[Requirements]:
    try:
        return Requirements(
            resources=_combine_resources(fleet_requirements.resources, run_requirements.resources),
            max_price=_get_optional_min(fleet_requirements.max_price, run_requirements.max_price),
            spot=_combine_spot(fleet_requirements.spot, run_requirements.spot),
            reservation=_get_optional_single_value(
                fleet_requirements.reservation, run_requirements.reservation
            ),
        )
    except CombineError:
        return None


T = TypeVar("T")
CompT = TypeVar("CompT", bound=Union[float, int])
StrT = TypeVar("StrT", bound=str)


def _intersect_lists(list1: Optional[list[T]], list2: Optional[list[T]]) -> Optional[list[T]]:
    if list1 is None:
        if list2 is None:
            return None
        return list2.copy()
    if list2 is None:
        return list1.copy()
    return [x for x in list1 if x in list2]


def _get_optional_min(value1: Optional[CompT], value2: Optional[CompT]) -> Optional[CompT]:
    if value1 is None:
        if value2 is None:
            return None
        return value2
    if value2 is None:
        return value1
    return min(value1, value2)


def _get_optional_single_value(value1: Optional[T], value2: Optional[T]) -> Optional[T]:
    if value1 is None:
        if value2 is None:
            return None
        return value2
    if value2 is None:
        return value1
    if value1 == value2:
        return value1
    raise CombineError(f"Values {value1} and {value2} cannot be combined")


def _combine_idle_duration(value1: Optional[int], value2: Optional[int]) -> Optional[int]:
    if value1 is None:
        if value2 is None:
            return None
        return value2
    if value2 is None:
        return value1
    if value1 < 0 and value2 >= 0 or value2 < 0 and value1 >= 0:
        raise CombineError(f"idle_duration values {value1} and {value2} cannot be combined")
    return min(value1, value2)


def _combine_resources(value1: ResourcesSpec, value2: ResourcesSpec) -> ResourcesSpec:
    return ResourcesSpec(
        cpu=_combine_cpu(value1.cpu, value2.cpu),  # converted by validator
        memory=_combine_memory(value1.memory, value2.memory),
        shm_size=_combine_shm_size(value1.shm_size, value2.shm_size),
        gpu=_combine_gpu(value1.gpu, value2.gpu),
        disk=_combine_disk(value1.disk, value2.disk),
    )


def _combine_cpu(value1: CPUSpec, value2: CPUSpec) -> CPUSpec:
    return CPUSpec(
        arch=_get_optional_single_value(value1.arch, value2.arch),
        count=_combine_range(value1.count, value2.count),
    )


def _combine_memory(value1: Range[Memory], value2: Range[Memory]) -> Range[Memory]:
    return _combine_range(value1, value2)


def _combine_shm_size(value1: Optional[Memory], value2: Optional[Memory]) -> Optional[Memory]:
    return _get_optional_min(value1, value2)


def _combine_gpu(value1: Optional[GPUSpec], value2: Optional[GPUSpec]) -> Optional[GPUSpec]:
    if value1 is None:
        if value2 is None:
            return None
        return value2.copy(deep=True)
    if value2 is None:
        return value1.copy(deep=True)
    return GPUSpec(
        vendor=_get_optional_single_value(value1.vendor, value2.vendor),
        name=_intersect_lists(value1.name, value2.name),
        count=_combine_range(value1.count, value2.count),
        memory=_combine_range_optional(value1.memory, value2.memory),
        total_memory=_combine_range_optional(value1.memory, value2.memory),
        # TODO: min compute_capability
        compute_capability=_get_optional_single_value(
            value1.compute_capability, value2.compute_capability
        ),
    )


def _combine_disk(value1: Optional[DiskSpec], value2: Optional[DiskSpec]) -> Optional[DiskSpec]:
    if value1 is None:
        if value2 is None:
            return None
        return value2.copy(deep=True)
    if value2 is None:
        return value1.copy(deep=True)
    return DiskSpec(
        size=_combine_range(value1.size, value2.size),
    )


def _combine_spot(value1: Optional[bool], value2: Optional[bool]) -> Optional[bool]:
    if value1 is None:
        if value2 is None:
            return None
        return value2
    if value2 is None:
        return value1
    if value1 != value2:
        raise CombineError(f"spot values {value1} and {value2} cannot be combined")
    return value1


def _combine_range(value1: Range, value2: Range) -> Range:
    res = value1.intersect(value2)
    if res is None:
        raise CombineError(f"Ranges {value1} and {value2} cannot be combined")
    return res


def _combine_range_optional(value1: Optional[Range], value2: Optional[Range]) -> Optional[Range]:
    if value1 is None:
        if value2 is None:
            return None
        return value2.copy(deep=True)
    if value2 is None:
        return value1.copy(deep=True)
    return _combine_range(value1, value2)
