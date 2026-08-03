import argparse
from pathlib import Path
from typing import Optional

import jinja2

TEMPLATE_DIR_PATH = Path(__file__).parent.parent.joinpath(
    "src/dstack/_internal/core/backends/template"
)
BACKENDS_DIR_PATH = Path(__file__).parent.parent.joinpath("src/dstack/_internal/core/backends")
TEMPLATE_FILENAMES = ["backend.py", "compute.py", "configurator.py", "models.py"]


def main():
    parser = argparse.ArgumentParser(
        description="This script generates boilerplate code for a new backend"
    )
    parser.add_argument(
        "-n",
        "--name",
        help=(
            "The backend name in CamelCase, e.g. AWS, Runpod, VastAI."
            " It'll be used for naming backend classes, models, etc."
        ),
        required=True,
    )
    args = parser.parse_args()
    generate_backend_code(args.name)


def generate_backend_code(backend_name: str, backends_dir_path: Optional[Path] = None) -> Path:
    """
    Renders the scaffold templates for a new backend.

    Args:
        backend_name: The backend name in CamelCase, e.g. `VastAI`.
        backends_dir_path: Where to create the backend package. Defaults to the real backends
            directory; tests pass a temporary one.

    Returns:
        The path of the generated backend package.
    """
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(
            searchpath=TEMPLATE_DIR_PATH,
        ),
        keep_trailing_newline=True,
    )
    if backends_dir_path is None:
        backends_dir_path = BACKENDS_DIR_PATH
    backend_dir_path = backends_dir_path.joinpath(backend_name.lower())
    backend_dir_path.mkdir(parents=True, exist_ok=True)
    for filename in TEMPLATE_FILENAMES:
        template = env.get_template(f"{filename}.jinja")
        with open(backend_dir_path.joinpath(filename), "w+") as f:
            f.write(template.render({"backend_name": backend_name}))
    backend_dir_path.joinpath("__init__.py").write_text("")
    return backend_dir_path


if __name__ == "__main__":
    main()
