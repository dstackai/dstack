# Clouds

With `dstack`, you can run LLM workloads using compute resources from multiple cloud GPU providers. 
All you need to do is sign up with these providers, and then pass
their credentials to `dstack`.

### Why multiple clouds?

<div class="grid cards" markdown>
- <span>**GPU availability**
   Because of high demand, it's easier to obtain GPU from various cloud providers through a single interface.</span>
- <span>**GPU price**
   Leverage smaller cloud services (e.g., Lambda Cloud) and spot instances across larger providers.</span>
- <span>**No vendor lock-in**
   An open-source and cloud-agnostic interface enables easy switching between cloud providers.</span>
</div>

## Creating cloud accounts

First, you have to create accounts with each cloud provider.

Currently, `dstack` supports [AWS](https://portal.aws.amazon.com/billing/signup), 
[GCP](https://console.cloud.google.com/freetrial), 
[Azure](https://azure.microsoft.com/en-us/free), and [Lambda](https://cloud.lambdalabs.com/sign-up). 
To request support for more providers, please submit or upvote
relevant issues in [our tracker](https://github.com/dstackai/dstack/issues).

??? info "Applying for cloud credits"
    Startups can apply for extra credits, usually by reaching out directly to the provider in the case of smaller providers,
    or through a partner program (such as [NVIDIA Inception](https://www.nvidia.com/en-us/startups/)) for larger providers.

??? info "Requesting GPU quotas"

    Larger providers require you to request GPU quotas, essentially obtaining permission from their support
    team, prior to utilizing GPUs with your account. If planning to use GPU through credits, approval for the request might
    take extra time.
    
    Quotas need to be requested separately for each family of GPUs and for each region where GPU usage is intended.

    To use spot instances with certain cloud providers (e.g. AWS), you should request quotes
    for such instances separately.

## Configuring clouds with dstack

First, you need to start the `dstack` server, log in to the UI, open the project settings, and add a backend for each
cloud.

![](../../assets/images/dstack-hub-view-project-empty.png){ width=800 }

Configuring backends involves providing cloud credentials, and specifying storage.

<div class="grid cards" markdown>
- [**AWS**
   Learn how to set up an Amazon Web Services backend.
  ](../../reference/backends/aws/)
- [**GCP**
   Learn how to set up a Google Cloud backend.
  ](../../reference/backends/gcp/)
- [**Azure**
   Learn how to set up an Microsoft Azure backend.
  ](../../reference/backends/azure/)
- [**Lambda**
   Learn how to set up a Lambda Cloud backend.
  ](../../reference/backends/lambda/)

</div>

## Requesting resources

You can request resources using the [`--gpu`](../reference/cli/run.md#GPU) 
and [`--memory`](../reference/cli/run.md#MEMORY) arguments with `dstack run`, 
or through [`resources`](../reference/profiles.yml.md#RESOURCES) with `.dstack/profiles.yml`.

Both the [`dstack run`](../reference/cli/run.md) command and [`.dstack/profiles.yml`](../reference/profiles.yml.md)
support various other options, including requesting spot instances, defining the maximum run duration or price, and
more.

!!! info "Automatic instance discovery"
    Remember, you can't specify an instance type by name. Instead, ask for resources by GPU name or memory amount. 
    `dstack` will automatically select the suitable instance type from a cloud provider and region with the best
    price and availability.

<div class="termy small">

```shell
$ dstack run . -f llama-2/train.dstack.yml --gpu A100

 Configuration       llama-2/train.dstack.yml
 Min resources       2xCPUs, 8GB, 1xA100
 Max price           no
 Spot policy         auto
 Max duration        72h

 #  BACKEND  RESOURCES                      SPOT  PRICE
 2  lambda   30xCPUs, 200GB, 1xA100 (80GB)  yes   $1.1
 3  gcp      12xCPUs, 85GB, 1xA100 (40GB)   yes   $1.20582
 1  azure    24xCPUs, 220GB, 1xA100 (80GB)  yes   $1.6469
    ...

Continue? [y/n]:
```

</div>