# Setup for Development

## 1. Clone the repo:

```shell
git clone https://github.com/dstackai/dstack
cd dstack
```
   
## 2. (Recommended) Create a virtual environment:

```shell
python3 -m venv venv # Python 3.11+
source venv/bin/activate
```
   
## 3. Install `dstack` in editable mode:

```shell
pip install -e '.[all]'
```
   
## 4. Install documentation dependencies:

```shell
pip install -r requirements_doc.txt
```
   
## 5. (Recommended) Install pre-commits:

```shell
pre-commit install
```

## 6. Comment out the `typeset` plugin:

The `typeset` plugin is an insider plugin that may not be available for local development. To build the documentation locally, you need to comment out this plugin in the `mkdocs.yml` file:

```yaml
plugins:
  # - typeset  # Comment out this line for local development
```

## 7. Build the documentation:

For local development (without the `typeset` plugin):
```shell
mkdocs build
```

For production build (with the `typeset` plugin):
```yaml
plugins:
  # - typeset  # Comment out this line for local development
```

```shell
mkdocs build mkdocs.yml
```


# Contribute to Documentation ( Adding Examples, API Reference, etc.)

We use `mkdocs` to build the documentation. `mkdocs` and the related packages are installed as dev dependencies with `requirements_doc.txt`.

```shell
pip install -r requirements_doc.txt
```

`mkdocs` uses a priviledged plugin`typeset`. To test in local dev environment, you should comment out the `typeset` plugin.

To build the documentation, run the following command:

```shell
mkdocs build
```

During build process, `mkdocs` uses the scripts in `scripts/docs` to generate the API reference and the examples from the docstrings and the examples/ folder
 README files.

To preview the documentation, run the following command:

```shell
mkdocs serve
```

# Style Guide

When contributing to the documentation, please adhere to the following style guidelines:


## General Guidelines


## Markdown Formatting


## Code Examples


## Links and References


Remember to run `mkdocs serve` to preview your changes locally before submitting a pull request.