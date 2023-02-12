from pydantic import BaseModel
from typing import Optional, List, Dict, Union


class Hub(BaseModel):
    name: str
    backend: str
    config: str


class HubInfo(BaseModel):
    name: str
    backend: str


class UserInfo(BaseModel):
    user_name: str

