from oci.exceptions import (
    BaseRequestException,
    ClientError,
    CompositeOperationError,
    MultipartUploadError,
    ServiceError,
)

any_oci_exception = (
    BaseRequestException,
    ClientError,
    CompositeOperationError,
    MultipartUploadError,
    ServiceError,
)
