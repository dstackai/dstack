# Justfile for building and uploading dstack runner and shim
#
# Run `just` to see all available commands
#
# Configuration:
# - DSTACK_SHIM_UPLOAD_VERSION: Version of the runner and shim to upload
# - DSTACK_SHIM_UPLOAD_S3_BUCKET: S3 bucket to upload binaries to
#
# Build Process:
# - Runner is always built for linux/amd64
# - Shim can be built for any platform (defaults to host platform)
# - When uploading, shim is automatically built for linux/amd64
#
# Development Workflows:
# - Local Development:
#   * Use build recipes to build binaries for local testing
#   * See README.md for instructions on running dstack server with local binaries
#   * No need to upload binaries for local development
#
# - Remote Development:
#   * Use upload recipes to build and upload binaries to S3
#   * See README.md for instructions on running dstack server with uploaded binaries
#   * Upload is required for testing with standard backends (including SSH fleets)

default:
    @just --list

# Version of the runner and shim to upload
export version := env_var("DSTACK_SHIM_UPLOAD_VERSION")

# S3 bucket to upload binaries to
export s3_bucket := env_var("DSTACK_SHIM_UPLOAD_S3_BUCKET")

# Download URLs
export runner_download_url := "s3://" + s3_bucket + "/" + version + "/binaries/dstack-runner-linux-amd64"
export shim_download_url := "s3://" + s3_bucket + "/" + version + "/binaries/dstack-shim-linux-amd64"

# Shim build configuration
export shim_os := ""
export shim_arch := ""

# Build runner
[private]
build-runner-binary:
    #!/usr/bin/env bash
    set -e
    echo "Building runner for linux/amd64"
    cd {{source_directory()}}/cmd/runner && GOOS=linux GOARCH=amd64 go build
    echo "Runner build complete!"

# Build shim
[private]
build-shim-binary:
    #!/usr/bin/env bash
    set -e
    cd {{source_directory()}}/cmd/shim
    if [ -n "$shim_os" ] && [ -n "$shim_arch" ]; then
        echo "Building shim for $shim_os/$shim_arch"
        GOOS=$shim_os GOARCH=$shim_arch go build
    else
        echo "Building shim for current platform"
        go build
    fi
    echo "Shim build complete!"

# Build both runner and shim
build-runner: build-runner-binary build-shim-binary
    echo "Build complete! Linux AMD64 binaries are in their respective cmd directories."

# Clean build artifacts
clean-runner:
    rm -f {{source_directory()}}/cmd/runner/runner
    rm -f {{source_directory()}}/cmd/shim/shim
    echo "Build artifacts cleaned!"

# Run tests for runner and shim
test-runner:
    cd {{source_directory()}} && go test -v ./...

# Validate shim is built for linux/amd64
[private]
validate-shim-binary:
    #!/usr/bin/env bash
    set -e
    if ! file {{source_directory()}}/cmd/shim/shim | grep -q "ELF 64-bit LSB executable, x86-64"; then
        echo "Error: Shim must be built for linux/amd64 for upload"
        exit 1
    fi

# Upload both runner and shim to S3
upload-runner: upload-runner-binary upload-shim-binary

# Upload runner to S3
[private]
upload-runner-binary:
    #!/usr/bin/env bash
    set -e
    just build-runner-binary
    aws s3 cp {{source_directory()}}/cmd/runner/runner "{{runner_download_url}}" --acl public-read
    echo "Uploaded runner to S3"

# Upload shim to S3
[private]
upload-shim-binary:
    #!/usr/bin/env bash
    set -e
    just --set shim_os linux --set shim_arch amd64 build-shim-binary
    just validate-shim-binary
    aws s3 cp {{source_directory()}}/cmd/shim/shim "{{shim_download_url}}" --acl public-read
    echo "Uploaded shim to S3"
