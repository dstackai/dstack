# GPT-2

This tutorial will walk you through the main steps of using `dstack` on the example of finetuning the famous 
OpenAI's GPT-2.

!!! warning "Prerequisites"

    Before following this tutorial, make sure you've done these required steps:

    1. [Install CLI](quickstart.md#install-the-cli)
    2. Set up [on-demand runners](on-demand-runners.md) or [self-hosted runners](self-hosted-runners.md)

## Step 1: Clone Git repo

Now, that the `dstack` CLI is installed and runners are set up, go ahead and clone the [`github.com/dstackai/gpt-2`](https://github.com/dstackai/gpt-2)
repository.

## Step 2: Add Git credentials

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

This command sends the URL of your remote repository and your private key to `dstack.ai`. This information will be
securely shared with the runners that will run workflows.

!!! warning "Repository folder"
    Make sure to run all `dstack` CLI commands from the folder where your Git repository is checked out,
    and where your `.dstack/workflows.yaml` and `.dstack/variables.yaml` files are.

## Step 3: Run a workflow

If you type `dstack run --help`, you'll see the following output:

```bash
usage: dstack run [-h] {download-model,encode-dataset,finetune-model} ...

positional arguments:
  {download-model,encode-dataset,finetune-model}
    download-model      run download-model workflow
    encode-dataset      run encode-dataset workflow
    finetune-model      run finetune-model workflow
```

Here, the CLI shows you list of workflows that you have defined in your `.dstack/workflows.yaml` file.

If you type `dstack run download-model --help`, you'll see the following output:

```bash
dstack run download-model --help
usage: dstack run download-model [--model [MODEL]] [--models_dir [MODELS_DIR]]

optional arguments:
  --model [MODEL]              by default, the value is "124M"
  --models_dir [MODELS_DIR]̋̋̋    by default, the value is is "model"
```

Here, the CLI shows you the variables defined for the `download-model` workflow in `.dstack/variables.yaml`.

Now, let's go and run the `finetune-model` workflow:

```bash
dstack run finetune-model 
```

If you want, alternatively, you can override the default variable `model` with another value, e.g. `"117M"`:

```bash
dstack run finetune-model --model 117M 
```

This is how you override any variables that you have defined in `.dstack/variables.yaml`.

## Step 4: Check status

Once you've submitted a run, you can see its status, (incl. the jobs associated with it) with the help
of the `dstack status` command:

```bash
dstack status
```

Here's what you can see if you do that:

```bash
RUN            TAG     JOB           WORKFLOW        VARIABLES     SUBMITTED    RUNNER     STATUS
fast-rabbit-1  <none>                finetune-model  --model 117M  1 min ago    cricket-1  RUNNING
                       53881a211647  download-model  --model 117M  1 min ago    cricket-1  DONE
                       aa930d70645f  encode-dataset  --model 117M  1 min ago    cricket-1  DONE
                       59b05053abcb  finetune-model  --model 117M  1 min ago    cricket-1  RUNNING
```

!!! warning ""
    By default, the `dstack status` command lists all unfinished runs. If there are no unfinished runs,
    it lists the last finished run. If you'd like to see more finished runs, use the `--last <n>` argument to
    specify the number of last runs to show regardless of their status.

!!! warning "Job is not there?"
      In case you don't see your job in the list, it may mean one of the following: either, the job isn't created yet by 
      the `dstack` server, or there is a problem with your runners. 

## Step 4: Check logs

With the CLI, you can see the output of your run.
If you type `dstack logs --help`, you'll see the following output:

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

## Step 5: Stop jobs

Any job can be stopped at any time. If you type `dstack stop --help`, you'll see the following:

```bash
usage: dstack stop [--abort] (RUN | JOB)

positional arguments:
  (RUN | JOB)  run name or job id

optional arguments:
  --abort      abort the job (don't upload artifacts)
```

This command requires specifying an ID of a job or a name of a run. Also, if you want, you can specify the `--abort`
argument. In this case, `dstack` will not upload the output artifacts of the stopped job.

## Step 6: Check artifacts

Every job at the end of its execution stores its artifacts in the storage.
With the CLI, you can both list the contents of each artifact and download it to your local machine.

Here's how to list the content of the artifacts of a given job:

```bash
dstack artifacts <job id>
```

By default, it lists all individual files in each artifact.

If you want to see the total size of each artifact, use `-t` option:

```bash
dstack artifacts -t <job id>
```

If you'd like to download the artifacts, this can be done by the following command:

```bash
dstack artifacts <job id> --output <path to download artifacts>
```

## Step 7: Resume jobs

Any job that had been stopped can be resumed. This means, the job is restarted with its previously saved output
artifacts. If the job used checkpoints, it will be able to start the work where it stopped and not from the 
beginning.

If you've stopped the previously run `finetune-model` workflow, use this command to resume it:

```bash
usage: dstack resume JOB

positional arguments:
  JOB
```

The job will restore the earlier saved checkpoints and continue finetuning the model.