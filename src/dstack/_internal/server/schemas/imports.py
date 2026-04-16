from dstack._internal.core.models.common import CoreModel


class DeleteImportRequest(CoreModel):
    """
    Imports are unnamed, so they are deleted using the name and project of their export.
    """

    export_name: str
    export_project_name: str
