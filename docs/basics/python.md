# Python

!!! info "NOTE:"
    The source code for the examples below can be found on [GitHub](https://github.com/dstackai/dstack-examples).

The workflow below runs a Python script that prints `"Hello, world!"`:

=== "`.dstack/workflows/python.yaml`"

    ```yaml
    workflows:
      - name: hello-py
        provider: bash
        commands:
          - python python/hello.py
    ```

=== "`python/hello.py`"

    ```python
    if __name__ == '__main__':
        print("Hello, world!")
    ```

Run it locally using the `dstack run` command:

```shell hl_lines="1"
dstack run hello-py
```

You'll see the output in real-time as your workflow is running:

```shell hl_lines="1"
RUN           WORKFLOW  SUBMITTED  OWNER           STATUS     TAG 
slim-shady-1  hello-py  now        peterschmidt85  Submitted  
 
Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Hello, world
```

## Python packages

You can use both `pip` and `conda` within workflows install Python packages.

The workflow below installs `pandas` via `pip` and runs a Python script that uses `pandas`:

=== "`.dstack/workflows/python.yaml`"

    ```yaml
    workflows:
      - name: hello-pandas
        provider: bash
        commands:
          - pip install pandas
          - python python/hello_pandas.py
    ```

=== "`python/hello_pandas.py`"

    ```python
    import pandas as pd

    if __name__ == '__main__':
        df = pd.DataFrame(
            {
                "Name": [
                    "Braund, Mr. Owen Harris",
                    "Allen, Mr. William Henry",
                    "Bonnell, Miss. Elizabeth",
                ],
                "Age": [22, 35, 58],
                "Sex": ["male", "male", "female"],
            }
        )
    
        print(df)

    ```

Run it locally using the `dstack run` command:

```shell hl_lines="1"
dstack run hello-pandas
```

## Conda environments

You can create your custom Conda environments using `conda env create`, 
save them as artifact, and reuse from other workflows via `deps` and `conda activate`:

=== "`.dstack/workflows/conda.yaml`"

    ```yaml
    workflows:
      - name: setup-conda
        provider: bash
        commands:
          - conda env create --file conda/environment.yaml
        artifacts:
          - path: /opt/conda/envs/myenv
    
      - name: use-conda
        provider: bash
        deps:
          - workflow: setup-conda
        commands:
          - conda activate myenv
          - python conda/hello_pandas.py
    
    ```

=== "`conda/hello_pandas`"

    ```python
    import pandas as pd

    if __name__ == '__main__':
        df = pd.DataFrame(
            {
                "Name": [
                    "Braund, Mr. Owen Harris",
                    "Allen, Mr. William Henry",
                    "Bonnell, Miss. Elizabeth",
                ],
                "Age": [22, 35, 58],
                "Sex": ["male", "male", "female"],
            }
        )
    
        print(df)

    ```

First, run the `setup-conda` workflow:

```shell hl_lines="1"
dstack run setup-conda
```

And then, run the `use-conda` workflow:

```shell hl_lines="1"
dstack run use-conda
```

The `use-conda` workflow will reuse the `myenv` environment from the `setup-conda` workflow.

!!! warning "NOTE:"
    Conda environments are always bound to a specific architecture and cannot be reused on machines 
    that has a different architecture (e.g. `AMD64` vs `ARM64`).

## Python version

By default, the workflow uses the same Python version that you use locally. 
You can override the major Python version using the `python` property:

=== "`.dstack/workflows/python-version.yaml`"

    ```yaml
    workflows:
      - name: python-version
        provider: bash
        python: 3.7
        commands:
          - python --version
    ```

Run it locally using the `dstack run` command:

```shell hl_lines="1"
dstack run python-version
```