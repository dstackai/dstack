# Keep in sync with pyproject.toml and .github/workflows/build-artifacts.yml
supported_python_versions := '3.10,3.11,3.12,3.13,3.14'

install_tox_msg := '''
    tox is not installed; to install it using uv:
        uv tool install tox --with tox-uv
'''

python_version_msg := '''
    .python-version does not exist; to create (replace 3.14 with the desired version):
        * using uv:
            uv python pin 3.14
        * if uv is not used:
            echo 3.14 > .python-version
'''

[doc('''
    Run tests using the default environment
    The default Python version is set via .python-version file
''')]
[positional-arguments]
test-default *args: _check_tox_installed
    @if [ ! -f .python-version ]; then echo '{{python_version_msg}}' >&2; exit 1; fi
    tox run -e default "${@}"

[doc('Run tests against all supported Python versions')]
[positional-arguments]
test-supported *args: _check_tox_installed
    tox run -e {{supported_python_versions}} "${@}"

[doc('''
    Run tests using the current environment (no venv isolation)
    All dependencies must be already installed; a dummy environment is still created
''')]
[positional-arguments]
test-current *args: _check_tox_installed
    tox run -e dummy --skip-env-install "${@}"

@_check_tox_installed:
    if ! command -v 'tox' >/dev/null 2>&1; then echo '{{install_tox_msg}}' >&2; exit 1; fi

[default]
_list:
    @just --list {{module_path()}} --unsorted
