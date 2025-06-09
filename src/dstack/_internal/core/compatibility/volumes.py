from typing import Dict

from dstack._internal.core.models.volumes import VolumeConfiguration, VolumeSpec


def get_volume_spec_excludes(volume_spec: VolumeSpec) -> Dict:
    """
    Returns `volume_spec` exclude mapping to exclude certain fields from the request.
    Use this method to exclude new fields when they are not set to keep
    clients backward-compatibility with older servers.
    """
    spec_excludes = {}
    spec_excludes["configuration"] = _get_volume_configuration_excludes(volume_spec.configuration)
    return spec_excludes


def get_create_volume_excludes(configuration: VolumeConfiguration) -> Dict:
    """
    Returns an exclude mapping to exclude certain fields from the create volume request.
    Use this method to exclude new fields when they are not set to keep
    clients backward-compatibility with older servers.
    """
    create_volume_excludes = {}
    create_volume_excludes["configuration"] = _get_volume_configuration_excludes(configuration)
    return create_volume_excludes


def _get_volume_configuration_excludes(configuration: VolumeConfiguration) -> Dict:
    configuration_excludes = {}
    if configuration.tags is None:
        configuration_excludes["tags"] = True
    return configuration_excludes
