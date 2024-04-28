# Contributing to `dstack`

## 1. Set up your development environment

Follow [contributing/DEVELOPMENT.md](contributing/DEVELOPMENT.md)

## 2. Follow the contribution process

1. Look for an [existing issue](https://github.com/dstackai/dstack/issues) or create a [new one](https://github.com/dstackai/dstack/issues/new/choose)
2. Fork the repo
3. Commit your changes
4. Open a PR. [Link the PR to the issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/linking-a-pull-request-to-an-issue) (if you are solving one).

### 2.1 Before pushing your changes

We use [`ruff`](https://docs.astral.sh/ruff/) to format Python code and to sort Python imports. Before committing your changes, run:

1. `ruff check --fix`
2. `ruff format`

> There are also helper pre-commits installed for [`ruff`](https://docs.astral.sh/ruff/integrations/#pre-commit) that make commits fail if the code is not formatted or the imports are not sorted. They also change the code as required so that you can review the changes and commit again.

## 3. Add a new backend

If you'd like to integrate `dstack` with a new cloud 
provider, follow [contributing/BACKENDS.md](contributing/BACKENDS.md).

## 4. Share feedback

Feel free to open an [issue](https://github.com/dstackai/dstack/issues) if you encounter any difficulties contributing to `dstack`.
