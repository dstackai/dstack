## Run configurations

### Repo directory

It's now possible to specify the directory in the container where the repo is mounted:

```yaml
type: dev-environment

ide: vscode

repos:
  - local_path: .
    path: my_repo

  # or using short syntax:
  # - .:my_repo
```

The `path` property can be an absolute path or a relative path (with respect to `working_dir`). It's available inside run as the `$DSTACK_REPO_DIR` environment variable. If `path` is not set, the `/workflow` path is used.

### Working directory

Previously, the `working_dir` property had complicated semantics: it defaulted to the repo path (`/workflow`), but for tasks and services without `commands`, the image working directory was used. You could also specify custom `working_dir` relative to the repo directory. This is now reversed: you specify `working_dir` as absolute path, and the repo path can be specified relative to it. 

> [!NOTE]
> During transitioning period, the legacy behavior of using `/workflow` is preserved if `working_dir` is not set. In future releases, this will be simplified, and `working_dir`  will always default to the image working directory.

## Fleet configuration

###  Nodes, retry, and target

`dstack` now indefinitely maintains `nodes.min` specified for cloud fleets. If instances get terminated for any reason and there are fewer instances than `nodes.min`, `dstack` will provision new fleet instances in the background.

There is also a new `nodes.target` property that specifies the number of instances to provision on fleet apply. Since now `nodes.min` is always maintained, you may specify `nodes.target` different from `nodes.min` to provision more instances than needs to be maintained.

Example:

```yaml
type: fleet
name: default-fleet
nodes:
  min: 1 # Maintain one instance
  target: 2 # Provision two instances initially
  max: 3
```

`dstack` will provision two instances. After deleting one instance, there will be one instances left. Deleting the last instance will trigger `dstack` to re-create the instance.

## Offers

The UI now has a dedicated page showing GPU offers available across all configured backends.

<img width="750" src="https://github.com/user-attachments/assets/827b56d9-2b92-43d0-bb27-a7e6926b1b80" />

## Digital Ocean and AMD Developer Cloud

The release adds native integration with [DigitalOcean](https://www.digitalocean.com/products/gradient/gpu-droplets) and 
[AMD Developer Cloud](https://www.amd.com/en/developer/resources/cloud-access/amd-developer-cloud.html).

A backend configuration example:

```yaml
projects:
- name: main
  backends:
  - type: amddevcloud
    project_name: TestProject
    creds:
        type: api_key
        api_key: ...
```

For DigitalOcean, set `type` to `digitalocean`.

The `digitalocean` and `amddevcloud` backends support NVIDIA and AMD GPU VMs, respectively, and allow you to run 
[dev environments](../../docs/concepts/dev-environments.md) (interactive development), [tasks](../../docs/concepts/tasks.md) 
(training, fine-tuning, or other batch jobs), and [services](../../docs/concepts/services.md) (inference).

## Security

> [!IMPORTANT]
> This update fixes a vulnerability in the `cloudrift`, `cudo`, and `datacrunch` backends. Instances created with earlier `dstack` versions lack proper firewall rules, potentially exposing internal APIs and allowing unauthorized access.
>
> Users of these backends are advised to update to the latest version and re-create any running instances.

## What's changed

* Minor Hot Aisle Cleanup by @Bihan in https://github.com/dstackai/dstack/pull/2978
* UI for offers #3004 by @olgenn in https://github.com/dstackai/dstack/pull/3042
* Add `repos[].path` property by @un-def in https://github.com/dstackai/dstack/pull/3041
* style(frontend): Add missing final newline by @un-def in https://github.com/dstackai/dstack/pull/3044
* Implement fleet state-spec consolidation to maintain `nodes.min` by @r4victor in https://github.com/dstackai/dstack/pull/3047
* Add digital ocean and amd dev backend by @Bihan in https://github.com/dstackai/dstack/pull/3030
* test: include amddevcloud and digitalocean in backend types by @Bihan in https://github.com/dstackai/dstack/pull/3053
* Fix missing digitaloceanbase configurator methods by @Bihan in https://github.com/dstackai/dstack/pull/3055
* Expose job working dir via environment variable by @un-def in https://github.com/dstackai/dstack/pull/3049
* [runner] Ensure `working_dir` exists by @un-def in https://github.com/dstackai/dstack/pull/3052
* Fix server compatibility with pre-0.19.27 runners by @un-def in https://github.com/dstackai/dstack/pull/3054
* Bind shim and exposed container ports to localhost by @jvstme in https://github.com/dstackai/dstack/pull/3057
* Fix client compatibility with pre-0.19.27 servers by @un-def in https://github.com/dstackai/dstack/pull/3063
* [Docs] Reflect the repo and working directory changes (#3041) by @peterschmidt85 in https://github.com/dstackai/dstack/pull/3064
* Show a CLI warning when using autocreated fleets by @r4victor in https://github.com/dstackai/dstack/pull/3060
* Improve UX with private repos by @un-def in https://github.com/dstackai/dstack/pull/3065
* Set up instance-level firewall on all backends by @jvstme in https://github.com/dstackai/dstack/pull/3058
* Exclude target when equal to min for responses by @r4victor in https://github.com/dstackai/dstack/pull/3070
* [Docs] Shorten the default `working_dir` warning by @peterschmidt85 in https://github.com/dstackai/dstack/pull/3072
* Do not issue empty update for deleted_fleets_placement_groups by @r4victor in https://github.com/dstackai/dstack/pull/3071
* Exclude target when equal to min for responses (attempt 2) by @r4victor in https://github.com/dstackai/dstack/pull/3074


**Full changelog**: https://github.com/dstackai/dstack/compare/0.19.26...0.19.27
