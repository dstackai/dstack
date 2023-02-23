import re
import sys
from pathlib import Path

from setuptools import find_packages, setup

project_dir = Path(__file__).parent


def get_version():
    text = (project_dir / "cli" / "dstack" / "version.py").read_text()
    match = re.compile(r"__version__\s*=\s*\"?([^\n\"]+)\"?.*").match(text)
    if match:
        if match.group(1) != "None":
            return match.group(1)
        else:
            return None
    else:
        sys.exit("Can't parse version.py")


def get_long_description():
    return re.sub(
        r"<picture>\s*|<source[^>]*>\s*|\s*</picture>|<video[^>]*>\s*|</video>\s*|### Demo\s*",
        "",
        open(project_dir / "README.md").read(),
    )


setup(
    name="dstack",
    version=get_version(),
    author="Andrey Cheptsov",
    author_email="andrey@dstack.ai",
    package_dir={"": "cli"},
    packages=find_packages("cli"),
    package_data={
        "dstack.schemas": ["*.json"],
        "dstack.hub": ["statics/*", "statics/**/*", "statics/**/**/*"],
    },
    include_package_data=True,
    scripts=[],
    entry_points={
        "console_scripts": ["dstack=dstack.cli.main:main"],
    },
    url="https://dstack.ai",
    project_urls={
        "Source": "https://github.com/dstackai/dstack",
    },
    description="An open-source tool for teams to build reproducible ML workflows",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    python_requires=">=3.7",
    install_requires=[
        "pyyaml",
        "requests",
        "gitpython",
        "boto3",
        "tqdm",
        "jsonschema",
        "botocore",
        "python-dateutil",
        "paramiko",
        "git-url-parse",
        "rich",
        "fastapi",
        "starlette",
        "uvicorn",
        "pydantic",
        "sqlalchemy",
        "websocket-client",
        "cursor",
        "simple-term-menu",
        "py-cpuinfo",
        "psutil",
        "jinja2",
        "pygtail",
        "packaging",
    ],
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
        "Programming Language :: Python :: 3",
    ],
)
