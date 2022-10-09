import re
import sys
from pathlib import Path

from setuptools import setup, find_packages


def get_version():
    text = (Path("dstack") / "version.py").read_text()
    match = re.compile(r"__version__\s*=\s*\"?([^\n\"]+)\"?.*").match(text)
    if match and match.group(1) != "None":
        return match.group(1)
    else:
        sys.exit("Can't parse version.py")


setup(
    name="dstack",
    version=get_version(),
    author="Andrey Cheptsov",
    author_email="andrey@dstack.ai",
    packages=find_packages(),
    package_data={'dstack.dashboard': ['statics/*', 'statics/**/*', 'statics/**/**/*']},
    include_package_data=True,
    scripts=[],
    entry_points={
        "console_scripts": ["dstack=dstack.cli.main:main"],
    },
    url="https://dstack.ai",
    project_urls={
        "Source": "https://github.com/dstackai/dstack",
    },
    description="A command-line utility to provision infrastructure for ML workflows",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    python_requires=">=3.6",
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
        "websocket-client",
        "cursor",
        "simple-term-menu",
    ],
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
        "Programming Language :: Python :: 3"
    ]
)
