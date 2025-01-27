# dstack Sky

If you don't want to host the `dstack` server or would like to access GPU from the `dstack` marketplace, 
sign up with [dstack Sky](../guides/dstack-sky.md).

### Set up the CLI

If you've signed up, open your project settings, and copy the `dstack config` command to point the CLI to the project.

![](https://raw.githubusercontent.com/dstackai/static-assets/main/static-assets/images/dstack-sky-project-config.png){ width=800 }

Then, install the CLI on your machine and use the copied command.

<div class="termy">

```shell
$ pip install dstack
$ dstack config --url https://sky.dstack.ai \
    --project peterschmidt85 \
    --token bbae0f28-d3dd-4820-bf61-8f4bb40815da
    
Configuration is updated at ~/.dstack/config.yml
```

</div>

### Configure clouds

By default, [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"} 
uses the GPU from its marketplace, which requires a credit card to be attached in your account
settings.

To use your own cloud accounts, click the settings icon of the corresponding backend and specify credentials:

![](https://raw.githubusercontent.com/dstackai/static-assets/main/static-assets/images/dstack-sky-edit-backend-config.png){ width=800 }

For more details on how to configure your own cloud accounts, check
the [server/config.yml reference](../reference/server/config.yml.md).

## What's next?

1. Follow [quickstart](../quickstart.md)
2. Browse [examples](https://dstack.ai/examples)
3. Join the community via [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd)
