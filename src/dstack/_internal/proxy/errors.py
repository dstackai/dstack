from fastapi import HTTPException, status


class ProxyError(HTTPException):
    """Errors in dstack-proxy that are caused by and should be reported to the user"""

    def __init__(self, detail: str, code: int = status.HTTP_400_BAD_REQUEST) -> None:
        super().__init__(detail=detail, status_code=code)


class UnexpectedProxyError(RuntimeError):
    """Internal errors in dstack-proxy that should have never happened"""

    pass
