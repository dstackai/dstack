import yaml
import os

from dstack.backend.local.common import get_object, put_object


def next_run_name_index(path: str, run_name: str) -> int:
    count = 0
    root = os.path.join(path, "run-names")
    key = f"{run_name}.yaml"
    try:
        obj = get_object(Root=root, Key=key)
        count = yaml.load(obj, Loader=yaml.FullLoader)["count"]
        put_object(Body=yaml.dump({"count": count + 1}), Root=root, Key=key)
    except IOError as e:
        return 0
    return count + 1
