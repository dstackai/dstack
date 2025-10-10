from dstack._internal.core.models.common import CoreModel


class GetFileArchiveByHashRequest(CoreModel):
    hash: str
