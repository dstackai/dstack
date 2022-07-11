# Setup

This guide will walk you through the main steps that you have to take before you can use dstack with your project. 

## Install the CLI

To run workflows, you'll need the dstack CLI. Here's how to install and configure it:

```bash
pip install dstack -U
dstack config --token <token> 
```

Your token value can be found in `Settings`:

[//]: # (![]&#40;images/dstack_quickstart_token.png&#41;{ lazy=true width="1060" })

## Add your cloud credentials

To let dstack provision infrastructure in your cloud account, you have to provide dstack the corresponding credentials. 
To do that, go to the `Settings`, and then `Clouds`.

![](images/dstack_on_demand_settings.png){ lazy=true width="1060" }

[//]: # (TODO: Elaborate on permissions)

## Add your Git credentials

In case your project repository is private, dstack would need the credentials to access it.

There are two ways to grant dstack access to your Git repository:

1. By granting dstack permissions to your GitHib repositories
2. By uploading a private SSH key to dstack

!!! info "SSH"
    If you cloned your project repository via SSH, you have to upload a private SSH key to dstack.

    You can check how you cloned your repository via the following command:

    ```bash
    git remote -v
    ```
    If you see that the URL starts with `git://`, then it's SSH. Otherwise, it's HTTP.

### Option 1: Grant dstack GitHub permissions 

If your repository is hosted on GitHub and if you cloned it via HTTPs, open `Settings`, then `Git` 
and make sure you've configured your GitHub account. To check if dstack has access to your repositories,
click the `Edit` icon next to your GitHub account.

### Option 2: Upload a private SSH key

If your project is cloned using SSH, in order to grant dstack access to your code, you have to upload your private 
SSH key to dstack.

For security reasons, it's recommended that you create a dedicated SSH key for dstack which later you can always 
revoke.

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

## Add secret variables

If you plan to use third-party services from your workflows, you can use dstack's secrets 
to securely store passwords and tokens and access them from your workflows via environment variables.

Adding secrets can be done via `Settings` | `Secrets`.

The configured secrets are passed to the workflows as environment variables. 

Here's an example of how you can access them from Python: 

```python
import os

wandb_api_key = os.environ.get("WANDB_API_KEY")
```