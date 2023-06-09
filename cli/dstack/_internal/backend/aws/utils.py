import time
from typing import Any, List

import botocore.exceptions


def retry_operation_on_service_errors(
    func, errors: List[str], max_retries: int = 3, delay: int = 1, *args, **kwargs
) -> Any:
    last_error = None
    for _ in range(max_retries):
        try:
            return func(*args, **kwargs)
        except botocore.exceptions.ClientError as e:
            last_error = e
            if e.response["Error"]["Code"] in errors:
                time.sleep(delay)
            else:
                raise e
    raise last_error
