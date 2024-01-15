from fastapi import HTTPException


class GatewayError(Exception):
    def http(self, code: int = 400, **kwargs) -> HTTPException:
        return HTTPException(
            code,
            {
                "error": self.__class__.__name__,
                "message": str(self),
                **kwargs,
            },
        )


class SSHError(GatewayError):
    pass


class NotFoundError(HTTPException):
    def __init__(self, message: str = "Not found", **kwargs):
        super().__init__(
            404,
            {
                "message": message,
                **kwargs,
            },
        )
