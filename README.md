<div align="center">
<img src="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/logo.svg" width="300px"/>    

An open-source tool for running data and ML workflows in the cloud
______________________________________________________________________

[![pypi](https://badge.fury.io/py/dstack.svg)](https://badge.fury.io/py/dstack)
[![License](https://img.shields.io/badge/licence-MPL%202.0-blue)](LICENSE)
[![slack](https://img.shields.io/badge/chat-on%20slack-e01563)](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)

[//]: # ([![twitter]&#40;https://img.shields.io/twitter/follow/dstackai.svg?style=social&label=Follow&#41;]&#40;https://twitter.com/dstackai&#41;)

</div>

## Getting started

### Install the CLI

The CLI can be installed on your local machine via pip:

```bash
pip install dstack
```

Once you install it, configure it by running the following command:

```bash
dstack config
```

It will ask you the AWS profile (if not specified, the `default` will be used), the S3 bucket 
where to store the state and artifacts, and the region where to create EC2 instances.

The configuration will be stored in `~/.dstack/config.yaml`:

```yaml
backend: aws
bucket: "my-dstack-workspace"
region: "eu-west-1"
```

### Run commands

Pass your commands to the CLI along with output artifacts and hardware requirements (e.g. number of CPUs, GPUs, memory size, etc.):

```bash
$ dstack run bash -c "pip install -r requirements.txt && python train.py" \
        --artifact "checkpoint" --gpu 1
```

Within a minute, dstack, will set up EC2 instances, fetch your current
Git repo (incl. not-committed changes), download the input artifacts,
run the commands, upload the output artifacts, and tear down the instances.

You'll see the output in realtime as if you ran it locally.

The artifacts are automatically stored in S3.

**Note**: The EC2 instances are automatically configured with the correct CUDA driver to use NVIDIA GPUs.

### Define workflows

You can pass commands directly to the CLI, or define them in the
`.dstack/workflows.yaml` file:

```yaml
workflows:
  - name: prepare
    provider: bash
    commands: 
      - "python prepare.py"
    artifacts: 
      - "data"

  - name: train
    deps:
      - prepare:latest
    provider: bash
    commands: 
      - "pip install -r requirements"
      - "python train.py"
    artifacts: 
      - "checkpoint"
    resources:
      memory: 64GB
      gpu: 4
```

And then, run any of the defined workflows by name:

```bash
$ dstack run train
```

### Providers

dstack allows to run not only run commands or applications but also other tools
or even dev environments. 

See the [Providers](https://docs.dstack.ai/providers/) page 
for more details.

## Use cases

### Infrastructure on-demand

Instead of configuring EC2 instances manually, and logging into them via SSH, run commands from your terminal, and dstack will set up and tear down cloud machines automatically.
 
### Version and reuse artifacts 

Assign tags to these artifacts to reuse the artifacts from other runs. 

### Developer experience

Use dstack from your IDE or terminal. 
dstack is fully-integrated with Git, and tracks your code (incl. not-committed changes).

## Documentation

- [Overview](https://docs.dstack.ai)
- [Quickstart](https://docs.dstack.ai/quickstart)
- [Providers](https://docs.dstack.ai/providers)
- [CLI](https://docs.dstack.ai/cli)

## Help

If you encounter bugs or would like to suggest features, please report them directly 
to the [issue tracker](https://github.com/dstackai/dstack/issues).

For questions and support, join the [Slack channel](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ).

## Licence

[Mozilla Public License 2.0](LICENSE.md)