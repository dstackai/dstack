from fastapi import HTTPException
from starlette.responses import JSONResponse


class GatewayError(Exception):
    def to_response(self, code: int = 400, **kwargs) -> JSONResponse:
        return JSONResponse(
            status_code=code,
            content={
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
