from dstack._internal.core.models.common import IncludeExcludeStrDictType
from dstack._internal.core.models.volumes import (
    AnyVolumeConfiguration,
    VolumeSpec,
)


def get_volume_spec_excludes(volume_spec: VolumeSpec) -> IncludeExcludeStrDictType:
    """
    Returns `volume_spec` exclude mapping to exclude certain fields from the request.
    Use this method to exclude new fields when they are not set to keep
    clients backward-compatibility with older servers.
    """
    spec_excludes: IncludeExcludeStrDictType = {}
    spec_excludes["configuration"] = _get_volume_configuration_excludes(volume_spec.configuration)
    return spec_excludes


def get_create_volume_excludes(configuration: AnyVolumeConfiguration) -> IncludeExcludeStrDictType:
    """
    Returns an exclude mapping to exclude certain fields from the create volume request.
    Use this method to exclude new fields when they are not set to keep
    clients backward-compatibility with older servers.
    """
    create_volume_excludes: IncludeExcludeStrDictType = {}
    create_volume_excludes["configuration"] = _get_volume_configuration_excludes(configuration)
    return create_volume_excludes


def _get_volume_configuration_excludes(
    configuration: AnyVolumeConfiguration,
) -> IncludeExcludeStrDictType:
    configuration_excludes: IncludeExcludeStrDictType = {}
    return configuration_excludes
