from typing import List

from google.cloud import exceptions, storage


def get_client(project_id: str) -> storage.Client:
    return storage.Client(project=project_id)


def get_or_create_bucket(storage_client: storage.Client, bucket_name: str):
    try:
        return storage_client.create_bucket(bucket_name)
    except exceptions.Conflict:
        return storage_client.bucket(bucket_name)


def put_object(bucket: storage.Bucket, object_name: str, data: str):
    blob = bucket.blob(object_name)
    blob.upload_from_string(data)


def read_object(bucket: storage.Bucket, object_name: str) -> str:
    blob = bucket.get_blob(object_name)
    with blob.open() as f:
        return f.read()


def delete_object(bucket: storage.Bucket, object_name: str):
    blob = bucket.blob(object_name)
    blob.delete()


def list_objects(bucket: storage.Bucket, prefix: str) -> List[str]:
    # TODO pagination
    blobs = bucket.client.list_blobs(bucket.name, prefix=prefix)
    object_names = [blob.name for blob in blobs]
    return object_names
