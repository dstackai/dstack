from typing import Dict

from fastapi import APIRouter, Depends
from fastapi import status, HTTPException
from fastapi.security import HTTPBearer
from fastapi.security.http import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from dstack.hub.db import metadata
from dstack.hub.db.users import User

router = APIRouter(prefix="/api/users", tags=["users"])

security = HTTPBearer()


@router.get("/info")
async def info(authorization: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    with Session(metadata.engine, expire_on_commit=False) as session:
        user = session.query(User).where(User.token == authorization.credentials).first()
        if user:
            return {"user_name": user.name}
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Token is invalid",
            )
