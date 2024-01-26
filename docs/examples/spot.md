# Spot instances

Cloud instances come in three types: `reserved` (for long-term commitments at a cheaper rate), `on-demand` (used as needed but
more expensive), and `spot` (cheapest, provided when available, but can be taken away when requested by someone else).

There are three cloud providers that offer spot instances: AWS, GCP, and Azure. 
Once you've [configured](../docs/installation/index.md) any of these, you can use spot instances 
for [dev environments](../docs/concepts/dev-environments.md), [tasks](../docs/concepts/tasks.md), and 
[services](../docs/concepts/services.md).

!!! info "NOTE:"
    Before you can use spot instances with AWS, GCP, and Azure, ensure you request the necessary quota 
    in the corresponding regions via a support ticket.

## Setting a spot policy

By default, for dev environments, `dstack` doesn't use spot instances. For
tasks and services, `dstack` uses spot instances only if they are available (falling back to on-demand otherwise).
This default behavior can be overriden. 

To use only spot instances, pass `--spot` to `dstack run`. 
To use spot instances only if they are available (and fallback to on-demand instances otherwise),
pass `--spot-auto`:

<div class="termy">

```shell
$ dstack run . --gpu 24GB --spot-auto
 Max price      -
 Max duration   6h
 Spot policy    auto
 Retry policy   no

 #  BACKEND  REGION       RESOURCES               SPOT  PRICE
 1  gcp      us-central1  4xCPU, 16GB, L4 (24GB)  yes   $0.223804
 2  gcp      us-east1     4xCPU, 16GB, L4 (24GB)  yes   $0.223804
 3  gcp      us-west1     4xCPU, 16GB, L4 (24GB)  yes   $0.223804
    ...

Continue? [y/n]:
```

</div>

## Setting a retry policy

If the requested instance is unavailable, the `dstack run` command will fail – unless you specify a retry policy.
This can be done via `--retry-limit`:

<div class="termy">

```shell
$ dstack run . --gpu 24GB --spot --retry-limit 1h
```

</div>

In this case, `dstack` will retry to find spot instances within one hour. All that time, the run will be marked as
pending.

!!! info "NOTE:"
    If you've set the retry duration and the spot instance is taken while your run was not 
    finished, `dstack` will restart it from scratch.

If you run a service using spot instances, the default retry duration is set to infinity.  

## Tips and tricks

1. The `--spot-auto` policy allows for the automatic use of spot instances when available, seamlessly reverting to
   on-demand instances if spots aren't accessible. You can enable it via `dstack run` or 
   via [`profiles.yml`](../docs/reference/profiles.yml.md).
2. You can use multiple cloud providers (incl. AWS, GCP, and Azure) and regions to increase the likelihood of
   obtaining a spot instance. However, in doing so, beware of data transfer costs if large volumes of data
   need to be loaded.
3. When using spot instances for training, ensure you save checkpoints regularly and load them if the run is restarted
   due to interruption.
 
   