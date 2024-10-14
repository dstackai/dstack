# Development setup

## 1. Clone the repo:

```shell
git clone https://github.com/dstackai/dstack
cd dstack
```

## 2. (Recommended) Create a virtual environment:

```shell
python3 -m venv venv
source venv/bin/activate
```

## 3. Install `dstack` in editable mode:

```shell
pip install -e '.[all]'
```

## 4. Install dev dependencies:

```shell
pip install -r requirements_dev.txt
```

## 5. (Recommended) Install pre-commits:

```shell
pre-commit install
```

## 6. Frontend

See [FRONTEND.md](FRONTEND.md) for the details on how to build and develop the frontend.

# Contribute to Documentation

We use `mkdocs` to build the documentation. `mkdocs` and the related packages are installed as dev dependencies with `requirements_dev.txt`.

`mkdocs` uses a priviledged plugin`typeset`. To test in local dev environment, you should comment out the `typeset` plugin.

To build the documentation, run the following command:

```shell
mkdocs build
```

During the build process, `mkdocs` uses the scripts in `scripts/docs` to generate the API reference and the examples from the docstrings and the examples' README files.

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

