# Contributing to `dstack`

We appreciate your interest in contributing to `dstack`! This document will help you get up to speed with `dstack` codebase and guide you through the contribution process.

## Set up your development environment

Follow [contributing/DEVELOPMENT.md](contributing/DEVELOPMENT.md).

## Learn dstack internals

If you make a non-trivial change to `dstack`, we recommend you learn about `dstack` internals. A good place to start is [contributing/ARCHITECTURE.md](contributing/ARCHITECTURE.md).

## Make a PR

1. Look for an [existing issue](https://github.com/dstackai/dstack/issues) or create a [new one](https://github.com/dstackai/dstack/issues/new/choose).
2. Fork the repo.
3. Commit your changes.
4. Open a PR. [Link the PR to the issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/linking-a-pull-request-to-an-issue) (if you are solving one).

### Accepted changes

* Bug fixes that address a clearly defined bug. Include steps to reproduce in the linked issue or the PR.
* New features. Before submitting a feature PR, create an issue with a proposal to discuss it with the core team and other interested parties.
* Minor fixes such as typos.
* [Examples](examples/README.md).

### Before pushing your changes

We use [`ruff`](https://docs.astral.sh/ruff/) to format Python code and to sort Python imports. Before committing your changes, run:

1. `uv run ruff check --fix`
2. `uv run ruff format`

> There are also helper pre-commits installed for [`ruff`](https://docs.astral.sh/ruff/integrations/#pre-commit) that make commits fail if the code is not formatted or the imports are not sorted. They also change the code as required so that you can review the changes and commit again.

### Run tests

It's recommended to run tests locally before running them in CI.
To run Python tests, first ensure you've install dev dependencies as described in [contributing/DEVELOPMENT.md](contributing/DEVELOPMENT.md).
Then you can do:

```shell
uv run pytest src/tests
```

(Optionally) By default, tests run against SQLite.
Use the `--runpostgres` flag to run the tests against Postgres as well:

```shell
uv run pytest src/tests --runpostgres
```

## Add a new backend

If you'd like to integrate a new cloud provider to `dstack`, follow [contributing/BACKENDS.md](contributing/BACKENDS.md).

## Get help

If you have any questions, you can always get help in our [Discord](https://discord.gg/u8SmfwPpMd) community.
