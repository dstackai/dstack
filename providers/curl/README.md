# dstack python provider

This provider downloads a file by a URL.

## Workflow 

Example:

```yaml
workflows:
  - name: download-dataset
    provider: curl
    url: https://github.com/karpathy/char-rnn/blob/master/data/tinyshakespeare/input.txt
    output: raw_dataset/input.txt
    artifacts:
      - raw_dataset
```

Here's the list of parameters supported by the provider:

| Parameter     | Required | Description                      |
|---------------|----------|----------------------------------|
| `url`         | Yes      | The URL of the file to download. |
| `output`      | Yes      | The path to store the file.      |
| `artifacts`   | No       | The list of output artifacts.    |

## Command line

```bash
usage: dstack run curl [-h] --artifact [ARTIFACT] -o [OUTPUT] URL
```

Example:

```bash
dstack run curl https://github.com/karpathy/char-rnn/blob/master/data/tinyshakespeare/input.txt -o raw_dataset/input.txt --artifact raw_dataset
```