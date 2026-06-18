# Justfile for building and uploading dstack runner and shim
#
# Run `just` to see all available commands
#
# Configuration:
# - DSTACK_SHIM_UPLOAD_VERSION: Version of the runner and shim to upload
# - DSTACK_SHIM_UPLOAD_S3_BUCKET: S3 bucket to upload binaries to
# - DSTACK_SHIM_BUILD_ARCH: Target architecture for runner and shim (defaults to amd64)
#
# Build Process:
# - Runner and shim are always built for linux (GOOS=linux is the only supported OS)
# - The target architecture is configurable via DSTACK_SHIM_BUILD_ARCH (or `just --set arch ...`)
# - CGO is enabled only for native builds (Linux host with a matching architecture);
#   otherwise it is disabled and DCGM support is dropped
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
export version := env("DSTACK_SHIM_UPLOAD_VERSION", "0.0.0")

# S3 bucket to upload binaries to
export s3_bucket := env("DSTACK_SHIM_UPLOAD_S3_BUCKET", "dstack-runner-downloads-stgn")

# Target architecture for runner and shim (GOOS is always linux)
export arch := env("DSTACK_SHIM_BUILD_ARCH", "amd64")

# Download URLs
export runner_download_url := "s3://" + s3_bucket + "/" + version + "/binaries/dstack-runner-linux-" + arch
export shim_download_url := "s3://" + s3_bucket + "/" + version + "/binaries/dstack-shim-linux-" + arch

# Go toolchain image for running tests in a container (keep in sync with go.mod)
export go_version := env("DSTACK_GO_VERSION", "1.25")

# Build runner
[private]
build-runner-binary:
    #!/usr/bin/env bash
    set -e
    echo "Building runner for linux/$arch"
    cd {{source_directory()}}/cmd/runner && CGO_ENABLED=0 GOOS=linux GOARCH=$arch go build -ldflags "-X 'main.Version=$version' -extldflags '-static'"
    echo "Runner build complete!"

# Build shim
[private]
build-shim-binary:
    #!/usr/bin/env bash
    set -e
    cd {{source_directory()}}/cmd/shim
    echo "Building shim for linux/$arch"
    host_arch=$(uname -m)
    case "$host_arch" in
        x86_64) host_arch=amd64 ;;
        aarch64 | arm64) host_arch=arm64 ;;
    esac
    if [ "$(uname -s)" = "Linux" ] && [ "$host_arch" = "$arch" ]; then
        CGO_ENABLED=1 GOOS=linux GOARCH=$arch go build -ldflags "-X 'main.Version=$version'"
    else
        echo "WARNING: Cross-compiling to linux/$arch, disabling CGO (DCGM unavailable)"
        CGO_ENABLED=0 GOOS=linux GOARCH=$arch go build -ldflags "-X 'main.Version=$version' -extldflags '-static'"
    fi
    echo "Shim build (version: $version) complete!"

# Build both runner and shim
build-runner: build-runner-binary build-shim-binary
    echo "Build complete! linux/$arch binaries are in their respective cmd directories."

# Clean build artifacts
clean-runner:
    rm -f {{source_directory()}}/cmd/runner/runner
    rm -f {{source_directory()}}/cmd/shim/shim
    echo "Build artifacts cleaned!"

# Run tests for runner and shim (native; requires a Linux host)
test-runner:
    cd {{source_directory()}} && go test -v ./...

# Run tests for runner and shim in a Linux container (use on macOS/Windows, where native builds are not available)
# Examples:
#   just test-runner-in-container                              # short suite, all packages
#   just test-runner-in-container -run TestPullImage ./internal/shim/
test-runner-in-container *args="-short ./...":
    docker run --rm -t \
        -v {{source_directory()}}:/src -w /src \
        -v dstack-go-mod:/go/pkg/mod \
        -v dstack-go-build:/root/.cache/go-build \
        -v /var/run/docker.sock:/var/run/docker.sock \
        golang:{{go_version}} \
        go test -race {{args}}

# Validate shim is built for the configured linux architecture
[private]
validate-shim-binary:
    #!/usr/bin/env bash
    set -e
    case "$arch" in
        amd64) expected="x86-64" ;;
        arm64) expected="ARM aarch64" ;;
        *) echo "Error: Unsupported arch '$arch'"; exit 1 ;;
    esac
    if ! file {{source_directory()}}/cmd/shim/shim | grep -q "ELF 64-bit LSB executable, $expected"; then
        echo "Error: Shim must be built for linux/$arch for upload"
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
    just build-shim-binary
    just validate-shim-binary
    aws s3 cp {{source_directory()}}/cmd/shim/shim "{{shim_download_url}}" --acl public-read
    echo "Uploaded shim to S3"
