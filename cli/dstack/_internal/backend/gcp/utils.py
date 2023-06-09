import re
import sys
from typing import Any

from google.api_core.extended_operation import ExtendedOperation


def wait_for_extended_operation(
    operation: ExtendedOperation, verbose_name: str = "operation", timeout: int = 300
) -> Any:
    """
    This method will wait for the extended (long-running) operation to
    complete. If the operation is successful, it will return its result.
    If the operation ends with an error, an exception will be raised.
    If there were any warnings during the execution of the operation
    they will be printed to sys.stderr.

    Args:
        operation: a long-running operation you want to wait on.
        verbose_name: (optional) a more verbose name of the operation,
            used only during error and warning reporting.
        timeout: how long (in seconds) to wait for operation to finish.
            If None, wait indefinitely.

    Returns:
        Whatever the operation.result() returns.

    Raises:
        This method will raise the exception received from `operation.exception()`
        or RuntimeError if there is no exception set, but there is an `error_code`
        set for the `operation`.

        In case of an operation taking longer than `timeout` seconds to complete,
        a `concurrent.futures.TimeoutError` will be raised.
    """
    result = operation.result(timeout=timeout)

    if operation.error_code:
        print(
            f"Error during {verbose_name}: [Code: {operation.error_code}]: {operation.error_message}",
            file=sys.stderr,
            flush=True,
        )
        print(f"Operation ID: {operation.name}", file=sys.stderr, flush=True)
        raise operation.exception() or RuntimeError(operation.error_message)

    return result


def is_valid_label_value(value: str) -> bool:
    if len(value) > 63:
        return False
    m = re.match(r"^[a-z\d_-]+$", value)
    return m is not None


def get_resource_name(resource_path: str) -> str:
    return resource_path.rsplit(sep="/", maxsplit=1)[1]


def get_subnet_region(subnet_resource: str) -> str:
    return subnet_resource.rsplit(sep="/", maxsplit=3)[1]


def get_subnet_name(subnet_resource: str) -> str:
    return subnet_resource.rsplit(sep="/", maxsplit=1)[1]


def get_service_account_email(project_id: str, name: str) -> str:
    return f"{name}@{project_id}.iam.gserviceaccount.com"


def get_service_account_resource(project_id: str, email: str) -> str:
    return f"projects/{project_id}/serviceAccounts/{email}"
