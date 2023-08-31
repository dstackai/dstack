import re
import sys
from pathlib import Path
from shutil import copytree
from subprocess import check_call

from setuptools import Command, find_packages, setup
from setuptools.command.build_py import build_py
from setuptools.command.develop import develop
from setuptools.command.sdist import sdist

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


BASE_DEPS = [
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
    "pydantic<=1.10.10",
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
    "grpcio>=1.50",  # indirect
    "filelock",
    "watchfiles",
    "docker>=6.0.0",
    "dnspython",
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


class BaseCommand(Command):
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def get_inputs(self):
        return []

    def get_outputs(self):
        return []


class NPM(BaseCommand):
    user_options = []

    hub_dir = project_dir / "hub"

    node_modules_dir = hub_dir / "node_modules"

    dist_dir = hub_dir / "dist"

    def should_run(self):
        # TODO: Check if build is up-to-date
        return True

    def run(self):
        if not self.should_run():
            print("Skipping `npm install` and `npm run build`")
            return

        print("Running `npm install`...")
        check_call(
            ["npm", "install"],
            cwd=project_dir / "hub",
            shell=False,
        )
        print("Running `npm run build`...")
        check_call(
            ["npm", "run", "build"],
            cwd=project_dir / "hub",
            shell=False,
        )
        print("Copying `hub/build` to `cli/dstack/_internal/hub/statics`...")
        copytree("hub/build", "cli/dstack/_internal/hub/statics", dirs_exist_ok=True)


def npm_first(cls, strict=True):
    class _Command(cls):
        def run(self):
            try:
                self.run_command("npm")
            except Exception:
                if strict:
                    raise
                else:
                    pass
            return super().run()

    return _Command


class CustomDevelopInstaller(develop):
    def run(self):
        if not self.uninstall:
            self.distribution.run_command("npm")
        super().run()


is_repo = (project_dir / ".git").exists()

setup(
    name="dstack",
    version=get_version(),
    author="Andrey Cheptsov",
    author_email="andrey@dstack.ai",
    package_dir={"": "cli"},
    packages=find_packages("cli"),
    package_data={
        "dstack._internal": [
            "schemas/*.json",
            "scripts/*.sh",
            "scripts/*.py",
        ],
        "dstack._internal.hub": [
            "statics/*",
            "statics/**/*",
            "statics/**/**/*",
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
    description="dstack is an open-source toolkit for running LLM workloads across any clouds.",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    python_requires=">=3.7",
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
    cmdclass={
        "build_py": npm_first(build_py, strict=is_repo),
        "sdist": npm_first(sdist, strict=True),
        "npm": NPM,
        "develop": CustomDevelopInstaller,
    },
)
