# Python API

## Artifacts

This API allows you to save and load data and models from the artifact storage.

### dstack.artifacts.upload

```python
def upload(local_path: str, artifact_path: Optional[str] = None,
           tag: Optional[str] = None)
```

Uploads the files located under the `local_path` folder as artifacts.

#### Argument reference

- `tag` – (Optional) If `tag` is not specified, artifacts are automatically attached to the current run.
    If `tag is specified`, artifacts are attached to the given tag name.
- `local_path` – (Optional) The path to a local folder with the files to upload.
- `artifact_path` – (Optional) The path under which the files will be stored.

#### Usage example:

```python
from dstack import artifacts

# Uploads files under "datasets/dataset1" as artifacts and attach them to the current run 
artifacts.upload("datasets/dataset1")

# Uploads files under "datasets/dataset1" as artifacts and creates a tag "my_tag"
artifacts.upload("datasets/dataset1", tag="my_tag")
```

### dstack.artifacts.download

```python
def download(run: Optional[str] = None, tag: Optional[str] = None,
             artifact_path: Optional[str] = None, local_path: Optional[str] = None)
```

Downloads artifact files of a given run or a tag.

#### Argument reference

One of the following arguments is required:

- `run` – The run to download the artifacts from
- `tag` – The tag to download the artifacts from

The following arguments are optional:

- `artifact_path` – (Optional) The path to the artifact files to download. 
    If not specified, all artifact files are downloaded.
- `local_path` – (Optional) The local path to save the files to.
    If not specified, files are downloaded to the current directory.

#### Usage example

```python
from dstack import artifacts

# Downloads all artifact files of a run to the current directory
artifacts.download(run="sharp-shrimp-1")

# Downloads all artifact files of the "my_tag" tag and saves them to "my_model"
artifacts.download(tag="my_tag", local_path="my_model")
```

!!! info "NOTE:"
    Currently, the Python API can only be used from dev environments and tasks.
