# dstack AMD SMI

An Ubuntu-based image with [AMD SMI](https://rocm.docs.amd.com/projects/amdsmi/en/latest/) preinstalled. Suitable for AMD GPU detection.

## Usage

```shell
docker run --rm --device /dev/kfd --device /dev/dri dstackai/amd-smi static
```
