from typing import Optional

from dstack._internal.proxy.lib.models import Project, Replica, Service


def make_project(name: str) -> Project:
    return Project(name=name, ssh_private_key="secret")


def make_service(
    project_name: str,
    run_name: str,
    domain: Optional[str] = None,
    https: Optional[bool] = None,
    auth: bool = False,
) -> Service:
    return Service(
        project_name=project_name,
        run_name=run_name,
        domain=domain,
        https=https,
        auth=auth,
        client_max_body_size=2**20,
        replicas=(
            Replica(
                id="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                app_port=80,
                ssh_destination="ubuntu@server",
                ssh_port=22,
                ssh_proxy=None,
            ),
        ),
    )
