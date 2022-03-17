## Define workflows

The `.dstack/workflows.yaml` file is a YAML file within your project files where you define your ML 
workflows, their commands, dependencies, output artifacts, etc.

Here's an example of `.dstack/workflows.yaml` (from the [GPT-2](gpt-2.md) tutorial):

```yaml
workflows:
  - name: download-model
    image: tensorflow/tensorflow:1.15.0-py3
    commands:
      - pip3 install -r requirements.txt
      - python3 download_model.py $model
    artifacts:
      - models
  
  - name: encode-dataset
    image: tensorflow/tensorflow:1.15.0-py3
    commands:
      - curl -O https://github.com/karpathy/char-rnn/blob/master/data/tinyshakespeare/input.txt
      - pip3 install -r requirements.txt
      - mkdir -p datasets
      - PYTHONPATH=src ./encode.py --model_name $model input.txt datasets/input.npy
    artifacts:
      - datasets
    depends-on:
      - download-model
  
  - name: finetune-model
    image: tensorflow/tensorflow:1.15.0-py3
    commands:
      - pip3 install -r requirements.txt
      - PYTHONPATH=src python3 train.py --run_name $run_name --model_name $model --dataset datasets/input.npy $variables_as_args
    artifacts:
      - checkpoint
      - samples
    depends-on:
      - download-model
      - encode-dataset
```

### Workflow variables

In `.dstack/variables.yaml`, you can define variables and their default values. These variables can be
referenced then from the `.dstack/workflows.yaml` file.

!!! tip "Environment variables"
    Variables can be accessed as environment variables from the workflow itself (must be in upper case).

You can define both global variables (shared by all workflows) and for each workflow individually.

Here's an example of `.dstack/variables.yaml`(from the [GPT-2](gpt-2.md) tutorial):

```yaml
variables:
  global:
    model: 124M
    models_dir: model

  finetune-model:
    combine: 50000
    encoding: utf-8
    batch_size: 1
    learning_rate: 0.00002
    accumulate_gradients: 1
    twremat_memlimit: 12GB
    optimizer: adam
    noise: 0.0
    top_k: 40
    top_p: 0.0
    restore_from: latest
    sample_every: 100
    sample_length: 1023
    sample_num: 1
    save_every: 1000
    val_batch_size: 2
    val_batch_count: 40
    val_every: 0
```

In addition to your own variables (that you've defined in `.dstack/variables`), `dstack` supports the following 
`system variables` that can be also used workflows:

* `$run_name` – the unique ID of the current run
* `$job_id` – the unique ID of the current job
* `$variables_as_args` - expands into all variables defined in `.dstack/variables.yaml` for that workflow,
  formatted as `--var_1_name var_1_value, --var_1_name var_1_value ...`; use this variable if you'd like to pass all
  variables into a command

## Run workflows

Before you can run and manage workflows of your project via the CLI, you have to authorize `dstack` to access
your Git remote repository. 

### Add Git credentials

If you're connecting to your GitHub repository via HTTPS, use the following command:

```bash
dstack init 
```

It will open your browser and prompt you to authorize `dstack` to access your repository. 

If you're connecting to your Git repository via an SSH key, to authorize `dstack` to access your repository, 
use the following command:

```bash
dstack init --private-key <path to your ssh key> 
```

This command sends the URL of your remote repository and your private key to `dstack`. This information will be
securely shared with the runners that will run workflows.

!!! warning "Repository folder"
    Make sure to run all `dstack` CLI commands from the folder where your Git repository is checked out,
    and where your `.dstack/workflows.yaml` and `.dstack/variables.yaml` files are.

### Run workflows

If you type `dstack run --help`, you'll see the syntax of the run command as well as the list of the workflows
defined with `.dstack/workflows.yaml` that you can run. 

Here's an example (from the [GPT-2](gpt-2.md) tutorial):

```bash
usage: dstack run {download-model,encode-dataset,finetune-model} ...

positional arguments:
    download-model      run download-model workflow
    encode-dataset      run encode-dataset workflow
    finetune-model      run finetune-model workflow
```

If you type `dstack run <workflow name> --help`, you'll see that `dstack` is also aware of the variables defined
in `.dstack/variables.yaml` for that workflow. 

Here's an example (again, from the [GPT-2](gpt-2.md) tutorial):

```bash
usage: dstack run download-model [--model [MODEL]] [--models_dir [MODELS_DIR]]

optional arguments:
  --model       [MODEL]       default is 124M
  --models_dir  [MODELS_DIR]  default is model
```

If you want to run `download-model` from the example above and override the `model` variable, try this:

```bash
dstack run download-model --model 117M
```

!!! info "What happens when you run a workflow?"
    1. When you run a workflow using the `dstack run` command, `dstack` sends the run requests to `dstack`. 
    The request contains the information about the repository (incl. the branch, the commit hash of the head,
    uncommitted changes if any, etc.), the name of the workflow, and the overridden variable values.
    2. Once the `dstack` server receives a run request, it creates a list of jobs (one job per workflow that has to run).
    Then, `dstack` assigns each job to one of the available runners. If any of the workflows (one that you run or one
    it depends on) had already run before with the code and variables, `dstack` won't create a new job and instead
    will reuse the one from cache.
    3. Each job is assigned to one of the available runners.
    4. Once a runner receives a job, it runs, upload logs in real-time, and in the end upload output artifacts.

### Check run status

Once you've submitted a run, you can see its status, (incl. the jobs associated with it) with the help
of the `dstack status` command:

```bash
dstack status
```

If call it, you'll see the following output:

```bash
RUN            TAG     JOB           WORKFLOW        VARIABLES     SUBMITTED    RUNNER     STATUS
fast-rabbit-1  <none>                finetune-model  --model 117M  1 min ago    cricket-1  DONE
                       53881a211647  download-model  --model 117M  1 min ago    cricket-1  DONE
```

!!! warning ""
    By default, the `dstack status` command lists all unfinished runs. If there are no unfinished runs,
    it lists the last finished run. If you'd like to see more finished runs, use the `--last <n>` argument to
    specify the number of last runs to show regardless of their status.

### Check logs

With the `dstack` CLI, you can see the output of the entire run or individual of any job associated with it by its job ID.

Type `dstack logs --help`, to see how to do it:

```bash
usage: dstack logs [--follow] [--since [SINCE]] (RUN | JOB)

positional arguments:
  (RUN | JOB)

optional arguments:
  --follow, -f          Whether to continuously poll for new logs. By default,
                        the command will exit once there are no more logs to
                        display. To exit from this mode, use Control-C.
  --since [SINCE], -s [SINCE]
                        From what time to begin displaying logs. By default,
                        logs will be displayed starting from ten minutes in
                        the past. The value provided can be an ISO 8601
                        timestamp or a relative time. For example, a value of
                        5m would indicate to display logs starting five
                        minutes in the past.
```

### Check artifacts

Every job at the end of its execution saves its artifacts in the storage.
With the `dstac` CLI, you can do both list the contents of each artifact and download artifacts to your local machine.

Here's how to list the content of the artifacts of a given job:

```bash
dstack artifacts <job id>
```

By default, it lists all individual files in each artifact.

If you want to see the total size of each artifact, use `-t` option:

```bash
dstack artifacts -t <job id>
```

If you'd like to download artifacts, use the following command:

```bash
dstack artifacts <job id> --output <path to download artifacts>
```

!!! warning "Storage"
    By default, `dstack` stores output artifacts in its own secure storage that only your user has access to. 
    If you want to use your own storage, you can provide `dstack` 
    credentials to [your own AWS account](aws.md) (via `dstack aws config`) and specify your own S3 bucket
    to store output artifacts.

### Stop runs and jobs

Any submitted run or job can be stopped via the following command:

Type `dstack stop --help`, to see how to do it:

```bash
usage: dstack stop [-a] (RUN | JOB)

positional arguments:
  (RUN | JOB)

optional arguments:
  -a, --abort  Abort a run or job, i.e. don't upload artifacts
```

!!! tip "Abort"
    If you don't specify the `--abort` argument, the runner will try to gracefully stop the job and make sure all artifacts 
    and logs are collected. If you do specify the `--abort` argument, the runner will try to abort the job immediately.

When you stop a run or a job, they may get the status `STOPPING` or `ABORTING`, and only when they have fully stopped,
their status will change to `STOPPED` or `ABORTED`.

### Resume jobs

Any job that had been stopped can be resumed. This means, the job is restarted with its previously saved output
artifacts. If the job used checkpoints, it will be able to start the work where it stopped and not from the 
beginning.

Type `dstack resume --help`, to this command works:

```bash
usage: dstack resume JOB

positional arguments:
  JOB
```

!!! warning "Limitation"
    You can resume only those job that had been explicitly stopped and only if no other jobs depend on them.