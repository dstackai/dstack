<div align="center">
<img src="/docs/assets/logo.svg" width="200px"/>    

A provider that downloads the contents of a URL
______________________________________________________________________

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

</div>

# About

This provider downloads the contents of a URL. You can specify a URL to download from, a filename to save the URL contents as,
and finally which folders to save as output artifacts. 
.

## Workflows

Here's how to use this provider in `.dstack/workflows.yaml`:

```yaml
workflows:
  - name: download
    provider: curl
    url: https://github.com/karpathy/char-rnn/blob/master/data/tinyshakespeare/input.txt
    output: dataset/input.txt
    artifacts:
      - dataset
```

<details>
<summary>All workflow parameters supported by the provider</summary>

| Parameter     | Required | Description                      |
|---------------|----------|----------------------------------|
| `url`         | Yes      | The URL of the file to download. |
| `output`      | Yes      | The path to store the file.      |
| `artifacts`   | No       | The list of output artifacts.    |
</details>

## Command line

Here's how to use this provider from the command line:

```bash
usage: dstack run curl [-h] -a [ARTIFACT] -o [OUTPUT] URL
```

Example:

```bash
dstack run curl https://github.com/karpathy/char-rnn/blob/master/data/tinyshakespeare/input.txt -o dataset/input.txt -a dataset
```