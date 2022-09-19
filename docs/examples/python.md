# Python

The [`bash`](../reference/providers/bash.md), [`code`](../reference/providers/code.md), 
[`lab`](../reference/providers/lab.md), and [`notebook`](../reference/providers/notebook.md) providers
come with Python and Conda pre-installed.

This workflow runs a Python script.

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: hello-py
        provider: bash
        commands:
          - python hello.py
    ```

=== "hello.py"

    ```python
    print("Hello world")
    ```

By default, the provider uses the Python version `3.10`. You can change the major version using the `python` property:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: hello-py-39
        provider: bash
        python: 3.9
        commands:
          - python hello.py
    ```

=== "hello.py"

    ```python
    print("Hello world")
    ```

You can use the `pip` or the `conda` executables to install Python packages:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: hello-pandas
        provider: bash
        commands:
          - conda install pandas -y
          - python hello_pandas.py
    ```

=== "hello_pandas.py"

    ```python
    import pandas as pd

    data = {
      "calories": [420, 380, 390],
      "duration": [50, 40, 45]
    }
    
    #load data into a DataFrame object:
    df = pd.DataFrame(data)
    
    print(df) 
    ```