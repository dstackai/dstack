import json
import logging
from itertools import groupby
from pathlib import Path

import jsonschema
import pkg_resources
import yaml

from dstack.utils.common import PathLike

logger = logging.getLogger(__name__)


def load_workflows(dstack_dir: PathLike, skip_validation_errors: bool = False) -> dict:
    dstack_dir = Path(dstack_dir)
    files = []
    for pathname in [dstack_dir / "workflows.yaml", dstack_dir / "workflows.yml"]:
        if pathname.is_file():
            files.append(pathname)
    for pathname in dstack_dir.glob("workflows/*"):
        if pathname.suffix not in {".yaml", ".yml"} or not pathname.is_file():
            continue
        files.append(pathname)
    schema = json.loads(pkg_resources.resource_string("dstack.schemas", "workflows.json"))

    workflows = []
    for file in files:
        with file.open("r") as f:
            content = yaml.load(f, yaml.FullLoader)
        try:
            jsonschema.validate(content, schema)
        except jsonschema.ValidationError:
            logger.warning(f"Workflows validation error: {file}")
            if not skip_validation_errors:
                raise
            continue
        workflows.extend(content["workflows"] or [])

    workflows_dict = {}
    workflows.sort(key=lambda item: item["name"])
    for name, group in groupby(workflows, key=lambda item: item["name"]):
        group = list(group)
        if len(group) > 1:
            raise NameError(f"{len(group)} workflows with the same name `{name}`")
        workflows_dict[name] = group[0]
    return workflows_dict
