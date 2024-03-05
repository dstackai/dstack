from fastapi import APIRouter
from starlette.responses import JSONResponse

router = APIRouter()


@router.api_route("/{project}/services/{run_id}/fallback")
async def service_upstream_fallback(project: str, run_id: str):
    # TODO(egor-s): store event
    return JSONResponse(
        status_code=503,
        content={"message": "Service temporarily unavailable, try again later"},
    )
