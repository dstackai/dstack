# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
This script prepares a K8s cluster for dstack integration, namely:

    * Creates/updates required objects: a namespace, a service account, roles, etc.
    * Generates and prints a kubeconfig that can be used with dstack.

By default, a plain kubeconfig is generated. With `--output-format=dstack`, a dstack backend
config with kubeconfig contents embedded is generated.

The config is printed to stdout. Use shell redirects (`> /path/to/file`) to save it.

Example:

    # Generate a dstack backend config with the embedded kubeconfig data and save it to a file
    uv run scripts/setup_kubernetes.py --namespace dstack --output-format dstack > k8s.yml
    # Now you can copy k8s.yml's contents into the web UI project settings or server/config.yml
"""

import argparse
import base64
import logging
import os
import pathlib
import shlex
import subprocess
import tempfile
import textwrap
import time
from typing import Literal

REPO_DIR = pathlib.Path(__file__).parent.parent
MANIFESTS_DIR = REPO_DIR / "mkdocs/snippets/kubernetes"

# See MANIFESTS_DIR/*.yaml
ROLE_NAME = "dstack-backend"
NAMESPACE_PLACEHOLDER = "${NAMESPACE}"

DEFAULT_SERVICE_ACCOUNT_NAME = ROLE_NAME
DEFAULT_OUTPUT_FORMAT = "kubeconfig"
DEFAULT_LOG_LEVEL = "INFO"


class Kubectl:
    def __init__(self, kubeconfig: str | None = None, context: str | None = None) -> None:
        self._kubeconfig = kubeconfig
        self._context = context
        if context is None:
            logging.debug("using current-context")
            current_context = self.call("config", "current-context", capture_stdout=True)
            # Always use the once-resolved current-context to avoid in-flight context switching
            self._context = current_context

    @property
    def context(self) -> str:
        assert self._context is not None
        return self._context

    def call(self, *args: str, input: str | None = None, capture_stdout: bool = False) -> str:
        cmd = ["kubectl"]
        if self._kubeconfig is not None:
            cmd.extend(["--kubeconfig", self._kubeconfig])
        if self._context is not None:
            cmd.extend(["--context", self._context])
        cmd.extend(args)
        logging.debug("kubectl call: %s", shlex.join(cmd))
        cp = subprocess.run(cmd, text=True, input=input, stdout=subprocess.PIPE)
        output = cp.stdout.strip()
        if cp.returncode != 0:
            logging.error("kubectl command failed: %s", output)
            cp.check_returncode()
        if capture_stdout:
            return output
        logging.debug("kubectl output: %s", output)
        return ""

    def apply(self, manifest: str) -> None:
        manifest = textwrap.dedent(manifest).strip()
        logging.debug("applying manifest:\n%s", textwrap.indent(manifest, "  "))
        self.call("apply", "-f", "-", input=manifest)


def create_resources(
    *,
    kubectl: Kubectl,
    namespace: str,
    service_account_name: str,
    cluster_role_name: str,
    role_name: str,
) -> str:
    logging.info("creating required resources")

    # Namespace
    kubectl.apply(f"""
        apiVersion: v1
        kind: Namespace
        metadata:
          name: {namespace}
    """)

    # ServiceAccount
    kubectl.apply(f"""
        apiVersion: v1
        kind: ServiceAccount
        metadata:
          name: {service_account_name}
          namespace: {namespace}
    """)

    # Secret for service-account-token
    service_account_token_name = f"{service_account_name}-service-account-token"
    kubectl.apply(f"""
        apiVersion: v1
        kind: Secret
        metadata:
          name: {service_account_token_name}
          namespace: {namespace}
          annotations:
            kubernetes.io/service-account.name: {service_account_name}
        type: kubernetes.io/service-account-token
    """)
    for _ in range(10):
        token = kubectl.call(
            "get",
            "secret",
            service_account_token_name,
            "-n",
            namespace,
            "-o",
            "jsonpath={.data.token}",
            "--ignore-not-found",
            capture_stdout=True,
        )
        if token:
            break
        logging.debug("service account token does not exist yet, waiting")
        time.sleep(1)
    else:
        raise AssertionError(f"service account token does not exist: {service_account_token_name}")
    token = base64.b64decode(token).decode()

    # ClusterRole
    with open(MANIFESTS_DIR / "dstack-backend-clusterrole.yaml") as f:
        cluster_role_manifest = f.read()
    assert f" name: {cluster_role_name}\n" in cluster_role_manifest
    kubectl.apply(cluster_role_manifest)

    # ClusterRoleBinding
    kubectl.apply(f"""
        apiVersion: rbac.authorization.k8s.io/v1
        kind: ClusterRoleBinding
        metadata:
          name: {cluster_role_name}
        subjects:
          - kind: ServiceAccount
            name: {service_account_name}
            namespace: {namespace}
        roleRef:
          apiGroup: rbac.authorization.k8s.io
          kind: ClusterRole
          name: {cluster_role_name}
    """)

    # Role
    with open(MANIFESTS_DIR / "dstack-backend-role.yaml") as f:
        role_manifest = f.read()
    assert f" namespace: {NAMESPACE_PLACEHOLDER}\n" in role_manifest
    assert f" name: {role_name}\n" in role_manifest
    role_manifest = role_manifest.replace(NAMESPACE_PLACEHOLDER, namespace)
    kubectl.apply(role_manifest)

    # RoleBinding
    kubectl.apply(f"""
        apiVersion: rbac.authorization.k8s.io/v1
        kind: RoleBinding
        metadata:
          name: {role_name}
          namespace: {namespace}
        subjects:
          - kind: ServiceAccount
            name: {service_account_name}
            namespace: {namespace}
        roleRef:
          apiGroup: rbac.authorization.k8s.io
          kind: Role
          name: {role_name}
    """)

    logging.info("all resources created")
    return token


def generate_kubeconfig(
    *,
    kubectl: Kubectl,
    namespace: str,
    service_account_name: str,
    service_account_token: str,
) -> str:
    logging.info("generating kubeconfig")
    kubeconfig_content = kubectl.call("config", "view", "--minify", "--raw", capture_stdout=True)
    with tempfile.NamedTemporaryFile("w+") as f:
        f.write(kubeconfig_content)
        f.flush()
        tmp_kubectl = Kubectl(kubeconfig=f.name)
        old_user = tmp_kubectl.call(
            "config", "view", "-o", "jsonpath={.contexts[0].context.user}", capture_stdout=True
        )
        assert old_user
        tmp_kubectl.call("config", "delete-user", old_user)
        cluster = tmp_kubectl.call(
            "config", "view", "-o", "jsonpath={.contexts[0].context.cluster}", capture_stdout=True
        )
        assert cluster
        new_user = f"{cluster}-{service_account_name}"
        tmp_kubectl.call("config", "set-credentials", new_user, "--token", service_account_token)
        tmp_kubectl.call(
            "config", "set-context", "--current", "--user", new_user, "--namespace", namespace
        )
        logging.info("kubeconfig generated")
        return tmp_kubectl.call("config", "view", "--raw", capture_stdout=True)


class Args(argparse.Namespace):
    kubeconfig: str | None
    context: str | None
    namespace: str
    service_account: str
    output_format: Literal["kubeconfig", "dstack"]
    log_level: str


def parse_args() -> Args:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--kubeconfig",
        required=False,
        help="path to kubeconfig file (default: same as with kubectl)",
    )
    parser.add_argument(
        "--context",
        required=False,
        help="kubeconfig context to use (default: same as with kubectl)",
    )
    parser.add_argument(
        "--namespace",
        required=True,
        help="namespace for all resources managed by dstack (required)",
    )
    parser.add_argument(
        "--service-account",
        default=DEFAULT_SERVICE_ACCOUNT_NAME,
        help=f"name of dstack service account (default: {DEFAULT_SERVICE_ACCOUNT_NAME})",
    )
    parser.add_argument(
        "--output-format",
        choices=["kubeconfig", "dstack"],
        default=DEFAULT_OUTPUT_FORMAT,
        help=(
            "output format, kubeconfig for plain kubeconfig file,"
            " dstack for dstack backend config with embedded kubeconfig"
            f" (default: {DEFAULT_OUTPUT_FORMAT})"
        ),
    )
    parser.add_argument(
        "--log-level",
        default=DEFAULT_LOG_LEVEL,
        help=f"script logging level (default: {DEFAULT_LOG_LEVEL})",
    )
    return parser.parse_args(namespace=Args())


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=args.log_level.upper(), format="%(levelname)s: %(message)s")
    kubectl = Kubectl(kubeconfig=args.kubeconfig, context=args.context)
    if args.kubeconfig is not None:
        logging.info("using kubeconfig: %s", args.kubeconfig)
    elif kubeconfig_env_value := os.getenv("KUBECONFIG"):
        logging.info("using kubeconfig(s) from env: %s", kubeconfig_env_value)
    else:
        logging.info("using default kubeconfig")
    logging.info("using context: %s", kubectl.context)
    logging.info("using namespace: %s", args.namespace)
    whoami = kubectl.call("auth", "whoami", "-o", "name", capture_stdout=True)
    logging.debug("whoami: %s", whoami)
    service_account_token = create_resources(
        kubectl=kubectl,
        namespace=args.namespace,
        service_account_name=args.service_account,
        cluster_role_name=ROLE_NAME,
        role_name=ROLE_NAME,
    )
    generated_kubeconfig_content = generate_kubeconfig(
        kubectl=kubectl,
        namespace=args.namespace,
        service_account_name=args.service_account,
        service_account_token=service_account_token,
    )
    logging.info("generated config in `%s` format is printed to stdout\n", args.output_format)
    if args.output_format == "dstack":
        print(
            textwrap.dedent(f"""
                type: kubernetes
                namespace: {args.namespace}
                kubeconfig:
                  data: |
            """).strip()
        )
        print(textwrap.indent(generated_kubeconfig_content, "    "))
    else:
        print(generated_kubeconfig_content)


if __name__ == "__main__":
    main()
