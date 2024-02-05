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
    pip install -e '.[all]'
    ```
4. Install dev dependencies:
    ```
    pip install -r requirements_dev.txt
    ```
5. (Recommended) Install pre-commits:
    ```
    pre-commit install
    ```

## Contributing process

1. Look for an existing issue or create a new one.
2. Fork the repo.
3. Commit your changes.
4. Open a PR. [Link the PR to the issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/linking-a-pull-request-to-an-issue) if you are solving one.

## Making changes

We use [`ruff`](https://docs.astral.sh/ruff/) to format Python code and to sort Python imports. Before committing your changes, run:

1. `ruff --fix src`
2. `ruff format src`


There are also helper pre-commits installed for [`ruff`](https://docs.astral.sh/ruff/integrations/#pre-commit) that make commits fail if the code is not formatted or the imports are not sorted. They also change the code as required so that you can review the changes and commit again.

## Adding a new backend

Visit [How to add a backend](https://github.com/dstackai/dstack/wiki/How-to-add-a-backend) wiki page to learn how to add a new backend.

## P.S.

Feel free to open an issue if you have difficulties contributing to `dstack`.
