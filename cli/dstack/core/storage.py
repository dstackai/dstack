from typing import Optional

from pydantic import BaseModel


class StorageFile(BaseModel):
    filepath: str
    filesize_in_bytes: Optional[int]
