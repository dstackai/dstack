# Python API

`dstack` provides a Python API available within your running dev environments and tasks.
It allows you to use `dstack` features dynamically from your Python code, such as uploading and downloading artifacts while working in a dev environment.

The `dstack` Python API is not installed in the running environment by default. To access the API, install `dstack` explicitly:

```
pip install dstack[aws,azure,gcp]
```

!!! info "NOTE"
    You may specify only the backend that you use to speed up the install, e.g. `pip install dstack[aws]`.

## Artifacts API

The `dstack` Artifacts API allows you to upload and download artifact files from within your running dev environments and tasks.

#### upload

```python
def upload(local_path: str,
           artifact_path: Optional[str] = None,
           tag: Optional[str] = None)
```

Uploads files located at `local_path` as the artifacts of the current run.

If `tag` is specified, uploads the files as the artifacts of the tag instead.
By default, artifact files saved under the same path as `local_path`.
The `artifact_path` parameter can be used to specify a different artifact path.

Examples:
```python
# Uploads local_path as an artifact of the current run
artifacts.upload(local_path="datasets/dataset1")

# Uploads local_path as an artifact of a new run tagged as my_tag and saves it as artifact_path
artifacts.upload(local_path="datasets/dataset1", artifact_path="data", tag="my_tag")
```

**Arguments**:

- `local_path` (`str`): The local path to upload the files from
- `artifact_path` (`Optional[str]`): The path under which the files will be stored
- `tag` (`Optional[str]`): The tag to assign the artifacts, defaults to None

**Raises**:

- `ArtifactsUploadError`: Raises if cannot upload the artifacts
- `DstackError`: The base exception for all dstack errors

<a id="dstack.artifacts._artifacts.download"></a>

#### download

```python
def download(run: Optional[str] = None,
             tag: Optional[str] = None,
             artifact_path: Optional[str] = None,
             local_path: Optional[str] = None)
```

Downloads artifact files of a run or a tag.

The files are downloaded from `artifact_path` to `local_path`.
By default, downloads all the files and saves them to the current directory.

Examples:
```python
# Downloads all artifact files of a run
artifacts.download(run="sharp-shrimp-1")

# Downloads artifact files from artifact_path and saves them to local_path
artifacts.download(tag="my_tag", artifact_path="output/my_model", local_path="./my_model")
```

**Arguments**:

- `run` (`Optional[str]`): The run to download the artifacts from
- `tag` (`Optional[str]`): The tag to download the artifacts from
- `artifact_path` (`Optional[str]`): The path to artifact files to download, defaults to ""
- `local_path` (`Optional[str]`): The local path to save the files to, defaults to "."

**Raises**:

- `ArtifactsDownloadError`: Raises if cannot download the artifacts
- `DstackError`: The base exception for all dstack errors

