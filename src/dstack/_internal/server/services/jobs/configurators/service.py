from typing import List, Optional

from dstack._internal import settings
from dstack._internal.core.models.configurations import (
    PortMapping,
    ReplicaGroup,
    RunConfigurationType,
)
from dstack._internal.core.models.profiles import SpotPolicy
from dstack._internal.core.models.unix import UnixUser
from dstack._internal.server.services.jobs.configurators.base import (
    JobConfigurator,
    get_default_image,
)


class ServiceJobConfigurator(JobConfigurator):
    TYPE: RunConfigurationType = RunConfigurationType.SERVICE

    def _current_replica_group(self) -> Optional[ReplicaGroup]:
        assert self.run_spec.configuration.type == "service"
        for group in self.run_spec.configuration.replica_groups:
            if group.name == self.replica_group_name:
                return group
        return None

    def _shell_commands(self) -> List[str]:
        assert self.run_spec.configuration.type == "service"
        group = self._current_replica_group()
        if group is not None:
            return group.commands
        return self.run_spec.configuration.commands

    def _image_name(self) -> str:
        group = self._current_replica_group()
        if group is not None:
            if group.docker is True:
                return settings.DSTACK_DIND_IMAGE
            if group.image is not None:
                return group.image
            if group.nvcc is True:
                return get_default_image(nvcc=True)
        return super()._image_name()

    def _privileged(self) -> bool:
        group = self._current_replica_group()
        if group is not None:
            if group.docker is True:
                return True
            if group.privileged is not None:
                return group.privileged
        return super()._privileged()

    def _dstack_image_commands(self) -> List[str]:
        group = self._current_replica_group()
        if group is not None:
            if group.docker is True:
                return ["start-dockerd"]
            if group.image is not None:
                return []
        return super()._dstack_image_commands()

    def _shell(self) -> str:
        # Shell resolution order:
        #   1. If `shell:` is set explicitly, the base honors it.
        #   2. If this group sets `docker: true`, use /bin/bash — the
        #      DIND image ships bash, matching the service-level path.
        #   3. If this group sets its own `image`, force /bin/sh. The
        #      base returns /bin/bash when service-level `image` is None,
        #      but a group-level custom image (e.g. alpine) may not ship
        #      bash.
        #   4. Otherwise defer to the base (bash for dstackai/base, sh
        #      for a service-level custom image).
        if self.run_spec.configuration.shell is None:
            group = self._current_replica_group()
            if group is not None:
                if group.docker is True:
                    return "/bin/bash"
                if group.image is not None:
                    return "/bin/sh"
        return super()._shell()

    async def _user(self) -> Optional[UnixUser]:
        # Base `_user()` only queries the image for a default user when
        # `configuration.image` is set at the service level. When the
        # group supplies its own `image`, perform the lookup here so the
        # container runs as that image's default user.
        #
        # We intentionally do NOT look up the DIND image when the group
        # sets `docker: true`. That matches service-level behavior: when
        # `configuration.docker is True`, `configuration.image` is None,
        # so the base skips the lookup. DIND is always privileged and
        # effectively root anyway.
        if self.run_spec.configuration.user is None:
            group = self._current_replica_group()
            if group is not None and group.image is not None:
                image_config = await self._get_image_config()
                if image_config.user is None:
                    return None
                return UnixUser.parse(image_config.user)
        return await super()._user()

    def _python(self) -> str:
        group = self._current_replica_group()
        if group is not None and group.python is not None:
            return group.python.value
        return super()._python()

    def _default_single_branch(self) -> bool:
        return True

    def _default_max_duration(self) -> Optional[int]:
        return None

    def _spot_policy(self) -> SpotPolicy:
        return self.run_spec.merged_profile.spot_policy or SpotPolicy.ONDEMAND

    def _ports(self) -> List[PortMapping]:
        return []
