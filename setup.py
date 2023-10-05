import re
import sys
from pathlib import Path

from setuptools import find_packages, setup

project_dir = Path(__file__).parent


def get_version():
    text = (project_dir / "src" / "dstack" / "version.py").read_text()
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


BASE_DEPS = [
    "pyyaml",
    "requests",
    "typing-extensions>=4.0.0",
    "cryptography",
    "packaging",
    "python-dateutil",
    "gitpython",
    "jsonschema",
    "paramiko",
    "git-url-parse",
    "cursor",
    "rich",
    "rich-argparse",
    "tqdm",
    "simple-term-menu",
    "fastapi",
    "starlette>=0.26.0",
    "uvicorn",
    "pydantic<=1.10.10",
    "sqlalchemy[asyncio]>=2.0.0",
    "sqlalchemy_utils>=0.40.0",
    "alembic>=1.10.2",
    "apscheduler",
    "aiosqlite",
    "aiohttp",
    "websocket-client",
    "watchfiles",
    "python-multipart",
    "filelock",
    "docker>=6.0.0",
    "dnspython",
    "grpcio>=1.50",  # indirect
]

AWS_DEPS = [
    "boto3",
    "botocore",
]

AZURE_DEPS = [
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
]

GCP_DEPS = [
    "google-auth>=2.3.0",  # indirect
    "google-cloud-storage>=2.0.0",
    "google-cloud-compute>=1.5.0",
    "google-cloud-secret-manager>=2.0.0",
    "google-cloud-logging>=2.0.0",
    "google-api-python-client>=2.80.0",
    "google-cloud-billing>=1.11.0",
]

LAMBDA_DEPS = AWS_DEPS

ALL_DEPS = AWS_DEPS + AZURE_DEPS + GCP_DEPS


setup(
    name="dstack",
    version=get_version(),
    author="Andrey Cheptsov",
    author_email="andrey@dstack.ai",
    package_dir={"": "src"},
    packages=find_packages("src"),
    package_data={
        "dstack._internal.server": [
            "scripts/*.sh",
            "scripts/*.py",
        ],
    },
    include_package_data=True,
    scripts=[],
    entry_points={
        "console_scripts": ["dstack=dstack._internal.cli.main:main"],
    },
    url="https://dstack.ai",
    project_urls={
        "Source": "https://github.com/dstackai/dstack",
    },
    description="dstack is an open-source framework for orchestration GPU workloads and development of generative AI "
    "models across multiple clouds.",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    python_requires=">=3.8",
    install_requires=BASE_DEPS,
    extras_require={
        "all": ALL_DEPS,
        "aws": AWS_DEPS,
        "azure": AZURE_DEPS,
        "gcp": GCP_DEPS,
        "lambda": LAMBDA_DEPS,
    },
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
        "Programming Language :: Python :: 3",
    ],
)
