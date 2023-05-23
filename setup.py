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
        "dstack.hub": [
            "statics/*",
            "statics/**/*",
            "statics/**/**/*",
        ],
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
    description="Develop ML faster. Easily and cost-effectively run dev environments, pipelines, and apps on any cloud.",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    python_requires=">=3.7",
    install_requires=[
        "pyyaml",
        "requests",
        "gitpython",
        "tqdm",
        "jsonschema",
        "python-dateutil",
        "paramiko",
        "git-url-parse",
        "rich",
        "rich-argparse",
        "fastapi",
        "starlette>=0.26.0",
        "uvicorn",
        "pydantic",
        "sqlalchemy[asyncio]>=2.0.0",
        "websocket-client",
        "cursor",
        "simple-term-menu",
        "py-cpuinfo",
        "pygtail",
        "packaging",
        "aiosqlite",
        "apscheduler",
        "alembic>=1.10.2",
        "typing-extensions>=4.0.0",
        "file-read-backwards>=3.0.0",
        "psutil>=5.0.0",
        "cryptography",
        "grpcio>=1.50,<=1.54",  # indirect
    ],
    extras_require={
        "aws": [
            "boto3",
            "botocore",
        ],
        "azure": [
            "azure-identity>=1.12.0",
            "azure-keyvault-secrets>=4.6.0",
            "azure-storage-blob>=12.15.0",
            "azure-monitor-query>=1.2.0",
            "azure-mgmt-subscription>=3.1.1",
            "azure-mgmt-compute>=29.1.0",
            "azure-mgmt-network==23.0.0b2",
            "azure-mgmt-resource>=22.0.0",
            "azure-mgmt-authorization>=3.0.0",
            "azure-mgmt-storage>=21.0.0",
            "azure-mgmt-keyvault>=10.1.0",
            "azure-mgmt-loganalytics==13.0.0b6",
            "azure-mgmt-msi",
            "azure-mgmt-monitor",
            "azure-graphrbac",
        ],
        "gcp": [
            "google-auth>=2.3.0",  # indirect
            "google-cloud-storage>=2.0.0",
            "google-cloud-compute>=1.5.0",
            "google-cloud-secret-manager>=2.0.0",
            "google-cloud-logging>=2.0.0",
        ],
    },
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
        "Programming Language :: Python :: 3",
    ],
)
