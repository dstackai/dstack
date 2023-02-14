from pydantic import BaseModel


class StorageFile(BaseModel):
    filepath: str
    filesize_in_bytes: int
