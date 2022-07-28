import os
import shutil
from pathlib import Path

from setuptools import setup, find_packages


def get_version():
    text = (Path("dstack") / "version.py").read_text()
    return text.split("=")[1].strip()[1:-1]


parent_path = Path(os.path.dirname(os.getcwd()))
shutil.copyfile(parent_path / ".dstack" / "providers.yaml", Path("dstack") / "cli" / "providers.yaml")

setup(
    name="dstack",
    version=get_version(),
    author="peterschmidt85",
    author_email="andrey@dstack.ai",
    packages=find_packages(),
    package_data={'': ['providers.yaml', 'schema.yaml']},
    include_package_data=True,
    scripts=[],
    entry_points={
        "console_scripts": ["dstack=dstack.cli.main:main"],
    },
    url="https://dstack.ai",
    project_urls={
        "Source": "https://github.com/dstackai/dstack",
    },
    description="A Command Line Interface for https://dstack.ai",
    long_description=open("../README.md").read(),
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
    ],
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: Other/Proprietary License",
        "Programming Language :: Python :: 3"
    ]
)
