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
# - The target architecture is configurable via DSTACK_SHIM_BUILD_ARCH (or `just build --arch ...`)
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

# Version of the runner and shim to upload
version := env("DSTACK_SHIM_UPLOAD_VERSION", "0.0.0")

# S3 bucket to upload binaries to
s3_bucket := env("DSTACK_SHIM_UPLOAD_S3_BUCKET", "dstack-runner-downloads-stgn")

# Target architecture for runner and shim (GOOS is always linux)
arch := env("DSTACK_SHIM_BUILD_ARCH", "amd64")

# Go toolchain image for running tests in a container (keep in sync with go.mod)
go_version := env("DSTACK_GO_VERSION", "1.25")

[doc("Build both runner and shim")]
[arg("arch", long)]
build arch=arch: (build-runner-binary arch) (build-shim-binary arch)
    @echo "Build complete! linux/{{arch}} binaries are in their respective cmd directories."

[doc("Clean build artifacts")]
clean:
    rm -f ./cmd/runner/runner
    rm -f ./cmd/shim/shim
    @echo "Build artifacts cleaned!"

[doc("Run tests for runner and shim (native; requires a Linux host)")]
test:
    go test -v ./...

# Examples:
#   just test-in-container  # short suite, all packages
#   just test-in-container -run TestPullImage ./internal/shim/
[doc("Run tests for runner and shim in a Linux container (use on macOS/Windows, where native builds are not available)")]
test-in-container *args="-short ./...":
    docker run --rm -t \
        -v .:/src -w /src \
        -v dstack-go-mod:/go/pkg/mod \
        -v dstack-go-build:/root/.cache/go-build \
        -v /var/run/docker.sock:/var/run/docker.sock \
        golang:{{go_version}} \
        go test -race {{args}}

[doc("Upload both runner and shim to S3")]
[arg("arch", long)]
upload arch=arch: (upload-runner-binary arch) (upload-shim-binary arch)

[private]
[doc("Build runner")]
[arg("arch", long)]
[working-directory: "./cmd/runner"]
build-runner-binary arch=arch:
    @echo "Building runner for linux/{{arch}}"
    CGO_ENABLED=0 GOOS=linux GOARCH={{arch}} go build -ldflags "-X 'main.Version={{version}}' -extldflags '-static'"
    @echo "Runner build (version: {{version}}) complete!"

[private]
[doc("Build shim")]
[arg("arch", long)]
[working-directory: "./cmd/shim"]
build-shim-binary arch=arch:
    #!/usr/bin/env bash
    set -e
    echo "Building shim for linux/{{arch}}"
    host_arch=$(uname -m)
    case "$host_arch" in
        x86_64) host_arch=amd64 ;;
        aarch64 | arm64) host_arch=arm64 ;;
    esac
    if [ "$(uname -s)" = "Linux" ] && [ "$host_arch" = "{{arch}}" ]; then
        CGO_ENABLED=1 GOOS=linux GOARCH={{arch}} go build -ldflags "-X 'main.Version={{version}}'"
    else
        echo "WARNING: Cross-compiling to linux/{{arch}}, disabling CGO (DCGM unavailable)"
        CGO_ENABLED=0 GOOS=linux GOARCH={{arch}} go build -ldflags "-X 'main.Version={{version}}' -extldflags '-static'"
    fi
    echo "Shim build (version: {{version}}) complete!"

[private]
[doc("Validate shim is built for the configured linux architecture")]
[arg("arch", long)]
validate-shim-binary arch=arch:
    #!/usr/bin/env bash
    set -e
    case "{{arch}}" in
        amd64) expected="x86-64" ;;
        arm64) expected="ARM aarch64" ;;
        *) echo "Error: Unsupported arch '{{arch}}'"; exit 1 ;;
    esac
    if [[ ! -f ./cmd/shim/shim ]]; then
        echo "Error: Shim binary not found"
        exit 1
    fi
    if ! file ./cmd/shim/shim | grep -q "ELF 64-bit LSB executable, $expected"; then
        echo "Error: Shim must be built for linux/{{arch}} for upload"
        exit 1
    fi

[private]
[doc("Upload runner to S3")]
[arg("arch", long)]
upload-runner-binary arch=arch: (build-runner-binary arch)
    aws s3 cp ./cmd/runner/runner s3://{{s3_bucket}}/{{version}}/binaries/dstack-runner-linux-{{arch}} --acl public-read
    @echo "Uploaded runner to S3"

[private]
[doc("Upload shim to S3")]
[arg("arch", long)]
upload-shim-binary arch=arch: (build-shim-binary arch) (validate-shim-binary arch)
    aws s3 cp ./cmd/shim/shim s3://{{s3_bucket}}/{{version}}/binaries/dstack-shim-linux-{{arch}} --acl public-read
    @echo "Uploaded shim to S3"

[default]
[private]
default:
    @just --list --unsorted
