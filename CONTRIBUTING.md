# Contributing to `dstack`

We appreciate your interest in contributing to `dstack`! This document will help you get up to speed with `dstack` codebase and guide you through the contribution process.

## AI Assistance Notice

If you are using any kind of AI assistance while contributing to `dstack`,
**this must be disclosed in the pull request**, along with the extent to
which AI assistance was used.
As an exception, tab-completions and trivial PRs don't need to be disclosed.

An example disclosure:

> This PR was written primarily by Claude Code.

Failure to disclose this, makes it difficult to determine how much scrutiny to apply to the contribution. Please be respectful to maintainers and disclose AI assistance.

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
* [Examples](examples).

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

Alternatively, you can run tests via [tox](https://tox.wiki/) inside an isolated environment ensuring that the `dstack` package itself is built correctly and all requirements are specified and correct. tox and [just](https://just.systems/) must be already installed.

* Run tests in the default environment:

  ```shell
  just tox::test-default
  ```

  The Python version of the default environment is configured via the `.python-version` file in the repo root directory. Note, the same file [is used by uv](https://docs.astral.sh/uv/concepts/python-versions/#python-version-files).

* Run tests against all currently supported Python versions:

  ```shell
  just tox::test-supported
  ```

* Run tests in the _current_ environment:

  ```shell
  just tox::test-current
  ```

  It saves about 30-60 seconds at the cost of Python environment isolation (defeating the core purpose of tox) — no packages are built or installed, and, as a consequence, all dependencies must be already installed, but, unlike the plain pytest command, the process environment variables are still isolated.

It's possible to pass pytest arguments after the `--` separator (the arguments _before_ the separator are `tox run` arguments):

```shell
just tox::test-default -- -vvv --last-failed
```

## Add a new backend

If you'd like to integrate a new cloud provider to `dstack`, follow [contributing/BACKENDS.md](contributing/BACKENDS.md).

## What's next

You can find more subject-focused guides in the [contributing](contributing/) directory.

If you have any questions, you can always get help in our [Discord](https://discord.gg/u8SmfwPpMd) community.
