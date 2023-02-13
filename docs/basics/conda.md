# Conda

!!! info "NOTE:"
    The source code for the examples below can be found on [GitHub](https://github.com/dstackai/dstack-examples).

## Conda packages

You can use `conda` within workflows install Conda packages (under the hood, it uses [Miniforge](https://github.com/conda-forge/miniforge)).

The workflow below installs `pandas` via `conda` and runs a Python script that uses `pandas`:

=== "`.dstack/workflows/conda.yaml`"

    ```yaml
    workflows:
      - name: hello-conda
        provider: bash
        commands:
          - conda install pandas
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
dstack run hello-conda
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
          - python python/hello_pandas.py
    
    ```

=== "`conda/environment.yaml`"

    ```yaml
    name: myenv

    dependencies:
      - python=3.10
      - pandas
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
    Conda environments are always bound to a specific architecture and cannot be reused across machines 
    with different architectures (e.g. `AMD64` vs `ARM64`).
