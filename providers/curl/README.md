# dstack python provider

This provider downloads a file by a URL.

Here's the list of parameters supported by the provider:

| Parameter     | Required | Description                      |
|---------------|----------|----------------------------------|
| `url`         | Yes      | The URL of the file to download. |
| `output`      | Yes      | The path to store the file.      |
| `artifacts`   | No       | The list of output artifacts.    |

Example:

```bash
workflows:
  - name: download-dataset
    provider: curl
    url: https://github.com/karpathy/char-rnn/blob/master/data/tinyshakespeare/input.txt
    output: raw_dataset/input.txt
    artifacts:
      - raw_dataset
```