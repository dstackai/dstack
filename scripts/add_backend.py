import argparse
from pathlib import Path

import jinja2


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


def generate_backend_code(backend_name: str):
    template_dir_path = Path(__file__).parent.parent.joinpath(
        "src/dstack/_internal/core/backends/template"
    )
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(
            searchpath=template_dir_path,
        ),
        keep_trailing_newline=True,
    )
    backend_dir_path = Path(__file__).parent.parent.joinpath(
        f"src/dstack/_internal/core/backends/{backend_name.lower()}"
    )
    backend_dir_path.mkdir(exist_ok=True)
    for filename in ["backend.py", "compute.py", "configurator.py", "models.py"]:
        template = env.get_template(f"{filename}.jinja")
        with open(backend_dir_path.joinpath(filename), "w+") as f:
            f.write(template.render({"backend_name": backend_name}))
    backend_dir_path.joinpath("__init__.py").write_text("")


if __name__ == "__main__":
    main()
