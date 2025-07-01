# Secrets

Secrets allow centralized management of sensitive values such as API keys and credentials. They are project-scoped, managed by project admins, and can be referenced in run configurations to pass sensitive values to runs in a secure manner.

!!! info "Secrets encryption"
    By default, secrets are stored in plaintext in the DB.
    Configure [server encryption](../guides/server-deployment.md#encryption) to store secrets encrypted.

## Manage secrets

### Set

Use the `dstack secret set` command to create a new secret:

<div class="termy">

```shell
$ dstack secret set my_secret some_secret_value
OK
```

</div>

The same command can be used to update an existing secret:

<div class="termy">

```shell
$ dstack secret set my_secret another_secret_value
OK
```

</div>

### List

Use the `dstack secret list` command to list all secrets set in a project:

<div class="termy">

```shell
$ dstack secret
 NAME       VALUE  
 hf_token   ****** 
 my_secret  ******

```

</div>

### Get

The `dstack secret list` does not show secret values. To see a secret value, use the `dstack secret get` command:

<div class="termy">

```shell
$ dstack secret get my_secret
 NAME       VALUE             
 my_secret  some_secret_value 

```

</div>

### Delete

Secrets can be deleted using the `dstack secret delete` command:

<div class="termy">

```shell
$ dstack secret delete my_secret
Delete the secret my_secret? [y/n]: y
OK
```

</div>

## Use secrets

You can use the `${{ secrets.<secret_name> }}` syntax to reference secrets in run configurations. Currently, secrets interpolation is supported in `env` and `registry_auth` properties.

### `env`

Suppose you need to pass a sensitive environment variable to a run such as `HF_TOKEN`. You'd first create a secret holding the environment variable value:

<div class="termy">

```shell
$ dstack secret set hf_token {hf_token_value}
OK
```

</div>

and then reference the secret in `env`:

<div editor-title=".dstack.yml"> 

```yaml
type: service
env:
  - HF_TOKEN=${{ secrets.hf_token }}
commands:
  ...
```

</div>

### `registry_auth`

If you need to pull a private Docker image, you can store registry credentials as secrets and reference them in `registry_auth`:

<div editor-title=".dstack.yml"> 

```yaml
type: service
image: nvcr.io/nim/deepseek-ai/deepseek-r1-distill-llama-8b
registry_auth:
  username: $oauthtoken
  password: ${{ secrets.ngc_api_key }}
```

</div>
