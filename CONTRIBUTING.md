# dstack contributing guide

## Development setup

1. Clone the repo:
    ```
    git clone https://github.com/dstackai/dstack && cd dstack
    ```
2. (Recommended) Create a virtual environment:
    ```
    python3 -m venv venv
    ```
    ```
    source venv/bin/activate
    ```
3. Install `dstack` in editable mode:
    ```
    pip install -e .
    ```
4. Install dev dependencies:
    ```
    pip install -r cli/requirements_dev.txt
    ```
5. Build the frontend
    ```
    ./scripts/build_frontend.sh
    ```
5. (Recommended) Install pre-commits:
    ```
    pre-commit install
    ```

For more information on frontend development, see [hub/README.md](hub/README.md).

## Contributing process

1. Look for an existing issue or create a new one.
2. Fork the repo.
3. Commit your changes.
4. Open a PR. [Link the PR to the issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/linking-a-pull-request-to-an-issue) if you are solving one.

## Making changes

We use [`black`](https://github.com/psf/black) to format Python code and [`isort`](https://pycqa.github.io/isort/index.html) to sort Python imports. Before committing your changes, run:

1. `isort --settings-file pyconfig.toml cli `
2. `black --config pyconfig.toml cli`


There are also helper pre-commits installed for [`black`](https://black.readthedocs.io/en/stable/integrations/source_version_control.html) and [`isort`](https://pycqa.github.io/isort/docs/configuration/pre-commit.html) that make commits fail if the code is not formatted or the imports are not sorted. They also change the code as required so that you can review the changes and commit again.

## P.S.

Feel free to open an issue if you have difficulties contributing to `dstack`.
