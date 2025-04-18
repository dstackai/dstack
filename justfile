# Justfile for building and uploading dstack runner and shim
#
# Build Process:
# - Runner is always built for linux/amd64
# - Shim can be built for any platform (defaults to host platform)
# - When uploading, shim is automatically built for linux/amd64
#
# Upload Process:
# - Both runner and shim are uploaded to S3 with version prefix
# - Shim is validated to ensure it's built for linux/amd64 before upload
# - Upload commands automatically rebuild binaries before uploading
#
# Development Workflows:
# - Local Development:
#   * Use build recipes to build binaries for local testing
#   * See runner/README.md for instructions on running dstack server with local binaries
#   * No need to upload binaries for local development
#
# - Remote Development:
#   * Use upload recipes to build and upload binaries to S3
#   * See runner/README.md for instructions on running dstack server with uploaded binaries
#   * Upload is required for testing with standard backends (including SSH fleets)
#
# Common Commands:
# - just build: Build both runner and shim
# - just upload: Upload both runner and shim
# - just build-upload: Build and upload both
# - just upload-shim: Build and upload only shim
# - just upload-runner: Build and upload only runner

# Default recipe to display available commands
default:
    @just --list

# Export version variable
export version := "0.0.0"

# Shim build configuration
export shim_os := ""
export shim_arch := ""

# Download URLs
export runner_download_url := "s3://dstack-runner-downloads-stgn/" + version + "/binaries/dstack-runner-linux-amd64"
export shim_download_url := "s3://dstack-runner-downloads-stgn/" + version + "/binaries/dstack-shim-linux-amd64"

# Build runner
build-runner:
    #!/usr/bin/env bash
    set -e
    echo "Building runner for linux/amd64"
    cd runner/cmd/runner && GOOS=linux GOARCH=amd64 go build
    echo "Runner build complete!"

# Build shim
build-shim:
    #!/usr/bin/env bash
    set -e
    cd runner/cmd/shim
    if [ -n "$shim_os" ] && [ -n "$shim_arch" ]; then
        echo "Building shim for $shim_os/$shim_arch"
        GOOS=$shim_os GOARCH=$shim_arch go build
    else
        echo "Building shim for current platform"
        go build
    fi
    echo "Shim build complete!"

# Build both runner and shim
build: build-runner build-shim
    echo "Build complete! Linux AMD64 binaries are in their respective cmd directories."

# Clean build artifacts
clean:
    rm -f runner/cmd/runner/runner
    rm -f runner/cmd/shim/shim
    echo "Build artifacts cleaned!"

# Run tests for runner and shim
test:
    cd runner && go test -v ./...

# Validate shim is built for linux/amd64
validate-shim:
    #!/usr/bin/env bash
    set -e
    if ! file runner/cmd/shim/shim | grep -q "ELF 64-bit LSB executable, x86-64"; then
        echo "Error: Shim must be built for linux/amd64 for upload"
        exit 1
    fi

# Upload both runner and shim to S3
upload: upload-runner upload-shim

# Upload runner to S3
upload-runner:
    #!/usr/bin/env bash
    set -e
    just build-runner
    aws s3 cp runner/cmd/runner/runner "{{runner_download_url}}" --acl public-read
    echo "Uploaded runner to S3"

# Upload shim to S3
upload-shim:
    #!/usr/bin/env bash
    set -e
    just --set shim_os linux --set shim_arch amd64 build-shim
    just validate-shim
    aws s3 cp runner/cmd/shim/shim "{{shim_download_url}}" --acl public-read
    echo "Uploaded shim to S3"

# Build and upload both runner and shim to S3
build-upload: build upload 
