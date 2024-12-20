# GitHub Actions

This example shows how to use Github Actions to automate the execution of an AI workload (like a fine-tuning or training job), on your server where dstack is configured, which could be in the cloud or on-prem. 

> Note: Your server would typically run within a private network so you will need to modify the Github workflow example below to enable you access the server in your private network
> 

??? info "Prerequisites"
    [Install](https://dstack.ai/docs/installation) `dstack` on the server.


## Setting up GitHub Action

Store your server's user, ssh private key, host/public IP information as well as any other required environment variable for your AI task as secrets in GitHub Actions secrets.

![alt text](/docs/assets/images/examples-misc-gh-a-secrets.png)

## GitHub Action Workflow
Using the github actions workflow below you will SSH into your server (i.e., dstack configured GPU machine) and run your AI workload (i.e., a dstack task, in the case of this example, a fine-tuning task)

<div editor-title="examples/fine-tuning/axolotl/.dstack.yml">

```yaml
name: Run dstack Task # Name of the GitHub Actions workflow

on:
  push:
    branches: [ main, master ] # Trigger on pushes to main or master branches
  pull_request: 
    branches: [ main, master ] # Trigger on pull requests to main or master branches

jobs:
  run-ai-workload:
    name: dstack-task  # Name of the job in the workflow
    runs-on: ubuntu-latest  # The type of machine to run the job on

    steps:
      - name: Connect to your server where Dstack is running with SSH
        run: |
          # Create an SSH private key file with secure permissions
          install -m 600 -D /dev/null ~/.ssh/github-actions

          # Add the SSH private key from GitHub secrets to the file
          echo "${{ secrets.SSH_PRIVATE_KEY }}" > ~/.ssh/github-actions
          
          # Configure SSH settings for the connection
          cat >> ~/.ssh/config <<END
          Host github-actions
            HostName ${{ secrets.SSH_HOST }} # The SSH host, provided as a secret
            User ${{ secrets.SSH_USER }} # The SSH user, provided as a secret
            IdentityFile ~/.ssh/github-actions # Path to the private key file
            Port 22 # SSH port (default is 22)
            StrictHostKeyChecking no # Disable host key checking for simplicity
          END

      - name: Pull new changes of the repo with AI workload code into your server and run task with dstack
        run: |
            ssh github-actions '
              DEFAULT_BRANCH=$(git ls-remote --symref https://github.com/${{ github.repository }} HEAD | grep "^ref" | awk "{print \$2}" | sed "s#refs/heads/##")
              if [ -d "${{ github.repository }}/.git" ]; then
                cd ${{ github.repository }} && git pull origin $DEFAULT_BRANCH
              else
                rm -rf dstack && git clone -b $DEFAULT_BRANCH https://github.com/<"${{ github.repository }}">
              fi
            '

      - name: Initialize dstack on the server and run the AI task with dstack
        run: |
          ssh github-actions << 'EOF'
            # Set environment variables, if any 
            export <env-variable>=${{ secrets.<env-variable-name> }}
            export <env-variable>=${{ secrets.<env-variable-name> }}  
            ....
            
            # Activate the Python environment, initialize dstack, and apply the task configuration
            source <environment-name>/bin/activate
            cd ${{ github.repository }}
            dstack init
            dstack apply -f <path to dstack in your repo directory> --yes &
          EOF
```

</div>

## Source code

The source code for this example can be found in 
[`examples/misc/github-actions` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/misc/github-actions).