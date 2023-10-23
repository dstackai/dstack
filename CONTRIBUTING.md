# dstack Contributing Guide

## Development Setup

1. **Fork the `dstack` repository**:
   [Fork the `dstack` repository](https://docs.github.com/en/github/getting-started-with-github/fork-a-repo) to your own GitHub account. This gives you a copy of the repository in your account.

2. **Clone your fork locally**:

    ```bash
    git clone git@github.com:<your Github handle>/dstack.git
    cd dstack
    ```

3. **Set up a remote for the original `dstack` repository**:

    ```bash
    git remote add upstream https://github.com/dstackai/dstack.git
    ```

4. **Set up a virtual environment** (recommended):

    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

5. **Install `dstack` in editable mode**:

    ```bash
    pip install -e '.[all]'
    ```

6. **Install development dependencies**:

    ```bash
    pip install -r requirements_dev.txt
    ```

7. **Build the frontend** (optional):

    ```bash
    ./scripts/build_frontend.sh
    ```

8. **Install pre-commit hooks** (recommended). These hooks ensure that your code is formatted according to `dstack` standards before committing:

    ```bash
    pre-commit install
    ```

For more details on frontend development, see [hub/README.md](hub/README.md).

## Contributing Process

1. **Create a new branch**: Always create a new branch for your changes:

    ```bash
    git checkout -b a-descriptive-name-for-my-changes
    ```

    ⚠️ Important: Make sure you always work on a specific branch tied to the issue you're addressing, not the main branch!

2. **Commit and Push**: After making your changes, commit them to your branch and then push the branch to your fork.

3. **Pull Request (PR)**: Open a PR against the main `dstack` repository from your forked repository's specific branch.

5. **Open a Pull Request (PR)**: Visit your fork on GitHub and click the "New Pull Request" button. Ensure you [link the PR to the issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/linking-a-pull-request-to-an-issue) if you are addressing one.

## Code Standards

We use [`black`](https://github.com/psf/black) to format Python code and [`isort`](https://pycqa.github.io/isort/index.html) to sort Python imports. Before committing, ensure you:

1. Sort your imports:

    ```bash
    isort --settings-file pyconfig.toml cli
    ```

2. Format your code:

    ```bash
    black --config pyconfig.toml cli
    ```

**Note**: We have pre-commit hooks for [`black`](https://black.readthedocs.io/en/stable/integrations/source_version_control.html) and [`isort`](https://pycqa.github.io/isort/docs/configuration/pre-commit.html) that will notify you if the code isn't formatted correctly or if imports aren't sorted. They will also auto-format the code for you.

## Need Help?

If you encounter any issues or need clarification while contributing to `dstack`, please feel free to open an issue. We're here to help!
