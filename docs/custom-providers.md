# Custom providers

A provider is a program that defines how a workflow materializes into actual jobs that process and output data
according to the workflow parameters.

While dstack offers the built-in providers, the users of dstack can define and use custom providers. Read on to
learn how to build custom providers.

## Define providers

Providers must be defined in the `.dstack/providers.yaml` file.

### Syntax

The root element of the `.dstack/providers.yaml` file is always `providers`.

It's an array, where each item represents a `Provider` and may have the following parameters:

| Name       | Required         | Description                                        |
|------------|------------------|----------------------------------------------------|
| `name`     | :material-check: | The name of our workflow                           |
| `image`    | :material-check: | The name of the Docker image                       |
| `commands` | :material-check: | The list of the commands that start the `Provider` |

Here's an example:

=== ".dstack/providers.yaml"

    ```yaml
    providers:
        - name: curl
          image: python:3.9
          commands:
            - pip3 install -r providers/curl/requirements.txt
            - PYTHONPATH=providers python3 providers/curl/main.py
    ```

## Build providers

dstack offers a Python API to build custom providers.

Here's an example:

=== "providers/curl/main.py"

    ```python
    from typing import List
    
    from dstack import Provider, Job
    
    
    class CurlProvider(Provider):
        def __init__(self):
            super().__init__(schema="providers/curl/schema.yaml")
            self.url = self.workflow.data["url"]
            self.output = self.workflow.data["output"]
            self.artifacts = self.workflow.data["artifacts"]
    
        def create_jobs(self) -> List[Job]:
            return [Job(
                image_name="python:3.9",
                commands=[
                    f"curl {self.url} -o {self.output}"
                ],
                artifacts=self.artifacts
            )]
    
    
    if __name__ == '__main__':
        provider = CurlProvider()
        provider.start()

    ```

#### Define a schema YAML file (optional)

A provider may have any number of parameters, which users will have to fill in their `.dstack/workflows.yaml` file
when using the provider. For example, the `curl` provider from above has three parameters:
`url`, `output`, and `artifacts`.

If you want the provider to validate whether the parameters are filled correctly, you can define a provider
schema, e.g. the following way:

=== "providers/curl/schema.yaml"

    ```yaml
    type: object
    additionalProperties: false
    properties:
      url:
        type: string
      output:
        type: string
      artifacts:
        type: array
        items:
          type: string
    required:
      - url
      - output
    ```

#### Define a provider class

The next step is defining a Python class of your provider that must inherit from the `dstack.Provider` class.

Define the `__init__` function that initializes the provider and reads its parameters:

a. Call the function from the super class. If you defined a schema in the previous step, pass its path to the `schema`
argument.

b. Read the parameters of your provider from the `self.workflow.data` dictionary.

```python
def __init__(self):
    super().__init__(schema="providers/curl/schema.yaml")
    self.url = self.workflow.data["url"]
    self.output = self.workflow.data["output"]
    self.artifacts = self.workflow.data["artifacts"]
```

Implement the `create_jobs` function that creates the actual jobs. Use the `dstack.Job` class to create instances
of jobs.

```python
def create_jobs(self) -> List[Job]:
    return [Job(
        image_name="python:3.9",
        commands=[
            f"curl {self.url} -o {self.output}"
        ],
        artifacts=self.artifacts
    )]
```

The `dstack.Job` class has the following arguments:

| Name          | Type                          | Required         | Description                                                                                                 |
|---------------|-------------------------------|------------------|-------------------------------------------------------------------------------------------------------------|
| `image_name`  | `str`                         | :material-check: | The name of the Docker image of the `Job`                                                                   |
| `commands`    | `List[str]`                   | :material-check: | The list of the commands that start the container of the `Job`                                              |
| `working_dir` | `str`                         | :material-check: | The working directory of the `Job` container                                                                |
| `artifacts`   | `List[str]`                   |                  | The list of folders inside the `Job` container <br/>that has to be stored as output `Artifacts` of the `Job` |
| `ports`       | `List[int]`                   |                  | The list of ports exposed by the `Job` container                                                            |
| `resources`   | `dstack.ResourceRequirements` |                  | The resource required by the `Job`, incl. CPU, memory, and GPU                                              |
| `depends_on`  | `List[dstack.Job]`            |                  | The list of other `Jobs` the `Job` is pending on                                                            |

## Test providers

In order to test your provider, simply define a workflow that uses your provider in the same project repository.

Here's an example:

```yaml
workflows:
  - name: tinyshakespeare
    provider: curl
    url: https://github.com/karpathy/char-rnn/blob/master/data/tinyshakespeare/input.txt
    output: data/input.txt
    artifacts:
      - data
```

And then, run it:

```bash
dstack run tinyshakespeare
```

Once your run is assigned to a runner and starts running, you'll see the output of your provider in the logs 
of your run.

## Use providers

If you want to use a provider from another repository, use the following syntax.

Here's an example:
    
```yaml
workflows:
  - name: tinyshakespeare
    provider:
      repo: https://github.com/<github user>/<github repository>
      name: curl
    url: https://github.com/karpathy/char-rnn/blob/master/data/tinyshakespeare/input.txt
    output: data/input.txt
    artifacts:
      - data
```