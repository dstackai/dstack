# Setup

This guide will walk you through the main steps that you have to take before you can use dstack with your project. 

## Prerequisites

Before you'll follow this guide, ensure the following:

* You've [signed up](https://dstack.ai/signup) with dstack
* You have an existing AWS account (otherwise, [sign up](https://portal.aws.amazon.com/billing/signup) for AWS beforehand)
* You have Git installed locally
* You have Python 3.7 (or higher) and pip installed locally

!!! info ""
    Currently, dstack supports only AWS. GCP and Azure support is under a private beta. To 
    try GCP and Azure support, drop an email to `hello@dstack.ai`.

## Step 1: Link your AWS account

To let dstack provision the infrastructure required for your workflows in your AWS account, you have to provide
dstack the corresponding credentials. To do that, go to the `Settings`, and then `AWS`.

Here, provide `AWS Access Key ID` and `AWS Secret Access Key` that have the
[corresponding](runners.md#on-demand-runners) permissions to create EC2 instances in your AWS account.

Once you've provided the credentials, use the `Add limit` button to configure the limits:

![](images/dstack_on_demand_settings.png){ lazy=true width="1060" }

The limits tell dstack what maximum number of EC2 instances of the specific instance type and i particular region
dstack can provision.

## Step 2: Install the CLI

To run workflows, you'll need the dstack CLI. Here's how to install and configure it:

```bash
pip install dstack -U
dstack config --token <token> 
```

Your token value can be found in `Settings`:

![](images/dstack_quickstart_token.png){ lazy=true width="1060" }

## Step 3: Configure Git credentials

In order to run workflows remotely, dstack will need access to your project Git repository.

!!! info ""
    This is why you have to use the CLI from the directory where you cloned your project Git repository

There are two ways to grant dstack access to your Git repository:

1. By granting dstack permissions to your GitHib repositories
2. By uploading a private SSH key to dstack

!!! info ""
    Currently, the choice between these two options depends on how you cloned your project Git repository.
    If you cloned it via HTTPS, you have grant dstack permissions to your GitHub account.
    If you cloned your repository via SSH, you have to upload a private SSH key to dstack.

    The easiest way to see how you cloned your project Git repository is the following command:

    ```bash
    git remote -v
    ```
    If you see that the URL starts with `https://`, then it's HTTPS. Otherwise, it's SSH.

### Option 1: Grant dstack GitHub permissions 

In order to grant dstack permissions to your GitHub repositories, open `Settings` and click `Update permissions`.
You'll be redirected to GitHub and will be prompted to grant dstack permissions. There you can choose yourself
to which repositories you grant access.

If you don't see the `Update permissions` button, this may mean that your dstack account is not yet associated with
a GitHub account. In that case you'll see the `Link GitHub account` button. Use this button to link your dstack
account to your GitHub account.

### Option 2: Upload a private SSH key

If your project was cloned using SSH, in order to grant dstack access to your code, you'll have to upload your private 
SSH key that grants this access.

For security reasons, it's recommended that you create a dedicated SSH key for dstack which later you can always 
deactivate.

In order to upload the private SSH key, you have to run the following command:

```bash
dstack init --private-key <path-to-your-private-key>
```

In case your private key has a passphrase, you have to specify it too:

```bash
dstack init --private-key <path-to-your-private-key> --passphrase <passphrase>
```

If the private key is not correct, you'll see an authorization error. If there is no error, this means you're all set.

!!! info ""
    If your repository is cloned via SSH, you have to upload your private key even if the project is public.

!!! tip ""
    If you are not sure about how to best clone your Git repository, the easiest and most secure option
    is always cloning it via GitHub's CLI using HTTPS protocol.

## Step 4: Configuring secrets

If you plan to use third-party services from your workflows, you can use dstack's secrets 
to securely pass passwords and tokens.

Adding secrets can be done via `Settings`.

The configured secrets are passed to the workflows as environment variables. 

Here's an example of how you can access them from Python: 

```python
import os

wandb_api_key = os.environ.get("WANDB_API_KEY")
```