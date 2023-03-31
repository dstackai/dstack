# Conda

!!! info "NOTE:"
    The source code of this example is available in the [Playground](../playground.md). 

## Conda packages

You can use `conda` within workflows install Conda packages (under the hood, it uses [Miniforge](https://github.com/conda-forge/miniforge)).

Create the following Python script:

<div editor-title="usage/python/hello_pandas.py"> 

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

</div>

Now, define a workflow YAML file:

<div editor-title=".dstack/workflows/conda.yaml"> 

```yaml
workflows:
  - name: hello-conda
    provider: bash
    commands:
      - conda install pandas
      - python python/hello_pandas.py
```

</div>

Run it locally using the `dstack run` command:

<div class="termy">

```shell
$ dstack run hello-conda
```

</div>

## Conda environments

You can create your custom Conda environments using `conda env create`, 
save them as artifact, and reuse from other workflows via `deps` and `conda activate`.

Say you have the following Conda environment YAML file:

<div editor-title="usage/python/hello.py"> 

```yaml
name: myenv

dependencies:
  - python=3.10
  - pandas
```

</div>

Now, create the following workflow YAML file:

<div editor-title=".dstack/workflows/conda.yaml">

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
      - conda env list

```

</div>

Now, run the `setup-conda` workflow:

<div class="termy">

```shell
$ dstack run setup-conda
```

</div>

And then, run the `use-conda` workflow:

<div class="termy">

```shell
$ dstack run use-conda

conda environments:

base                     /opt/anaconda3
workflow                 /opt/conda/envs/workflow
myenv                *   /opt/conda/envs/myenv
```

</div>

The `use-conda` workflow reuses the `myenv` environment from the `setup-conda` workflow.

!!! warning "NOTE:"
    Conda environments are always bound to a specific architecture and cannot be reused across machines 
    with different architectures (e.g. `AMD64` vs `ARM64`).
