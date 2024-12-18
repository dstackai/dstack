# GitHub Actions

This example shows how to use Github Actions to automate the execution of an AI workload (like a fine-tuning or training job), on a dstack GPU configured server (multiclouds and on-prem). 

> Note: Your server should typically run within a private network so you will need to modify the Github workflow example below to enable you access the server in your private network
> 

??? info "Prerequisites"
    [Install](https://dstack.ai/docs/installation) `dstack` on the server.


## Setting up GitHub Action

Store your server User, ssh private key, host/public IP and any other reqiuired environment variable for your task as secrets in GitHub Actions secrets.

![alt text](/docs/assets/images/examples-misc-gh-a-secrets.png)

## GitHub Action Workflow
Using the workflow below you will SSH into your dstack GPU configured machine and run your AI workload (i.e a dstack fine-tuning task in this case)

<div editor-title="examples/fine-tuning/axolotl/.dstack.yml">

```yaml
name: Run dstack Task

on:
  push:
    branches: none  #[ main ] or [ master ]
  pull_request: 
    branches: none  #[ "branch name"]

jobs:
  run-ai-workload:
    name: dstack-task
    runs-on: ubuntu-latest

    steps:
          - name: Configure SSH to connent to your machine
            run: |
              install -m 600 -D /dev/null ~/.ssh/github-actions
              echo "${{ secrets.SSH_PRIVATE_KEY }}" > ~/.ssh/github-actions
              cat >> ~/.ssh/config <<END
              Host github-actions
                HostName ${{ secrets.SSH_HOST }}
                User ${{ secrets.SSH_USER }}
                IdentityFile ~/.ssh/github-actions
                Port 22
                StrictHostKeyChecking no
              END

          - name: Clone pull new chances of your repo with AI workload code
            run: |
                ssh github-actions '
                  DEFAULT_BRANCH=$(git ls-remote --symref https://github.com/dstackai/dstack HEAD | grep "^ref" | awk "{print \$2}" | sed "s#refs/heads/##")
                  if [ -d "dstack/.git" ]; then
                    cd dstack && git pull origin $DEFAULT_BRANCH
                  else
                    rm -rf dstack && git clone -b $DEFAULT_BRANCH https://github.com/dstackai/dstack
                  fi
                '
          - name: initialize dstack on the server and run dstack task
            run: ssh github-actions 'export HF_TOKEN=${{ secrets.HF_TOKEN }} && export WANDB_API_KEY=${{ secrets.WANDB_API_KEY }} && source dstack-env/bin/activate && cd dstack && dstack init && dstack apply -f examples/fine-tuning/axolotl/.dstack.yaml --yes &'

```

</div>

## Source code

The source code for this example can be found in 
[`examples/misc/github-actions` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/misc/github-actions).