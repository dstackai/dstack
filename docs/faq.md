# FAQs

#### What kind of ML workflows can I use dstack for?

dstack allows you to describe workflows as code and quickly run them anywhere (e.g. in a configured cloud) from the CLI.
You don't have to worry about infrastructure or data management.

Workflows can be pretty much anything: scripts, long-running jobs, and even applications.

#### Can dstack run workflows locally on my machine? 

Currently, dstack can run workflows only in a configured cloud account. We plan to 
allow running workflows locally too. Please upvote 
the corresponding [GitHub issue](https://github.com/dstackai/dstack/issues/95).

#### Can I use SSH to connect to a workflow?

No, you can't use SSH to connect to a running workflow. Instead, we recommend you
to use one of the workflow providers that allow to work with code interactively:
[`code`](reference/providers/bash.md), [`lab`](reference/providers/lab.md),
or [`notebook`](reference/providers/notebook.md).

#### Does dstack support GCP, Azure, or Kubernetes?

dstack doesn't support any of that yet. Please upvote 
the corresponding [GitHub issue](https://github.com/dstackai/dstack/issues?q=is%3Aissue+is%3Aopen+label%3Acloud-provider).

#### Why does dstack require the working directory to be a GitHub repo?

Indeed, currently the `dstack` CLI works only within directories that 
are GitHub repositories. If you'd like dstack to work within any directories, 
or if your repository is not on GitHub (e.g. you use BitBucket or GitLab), please
file a corresponding [GitHub issue](https://github.com/dstackai/dstack/issues/new/choose).

#### I want to contribute to dstack? Where do I start?

We're currently working on a document that describes how dstack works internally.
Meanwhile, you can start with the source code, and ask questions in our 
[Slack chat](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ).

If you'd like to discuss a technical question or collaboration, we run [office hours](https://calendly.com/dstackai/office-hours).
Feel free to book a slot to talk directly.

#### Who is behind dstack, and what is your business model?

Currently, we are a team of three engineers. Some of us previously worked many years at JetBrains.

dstack will always be free and open-source. It's inspired and motivated purely by the desire
to build a lightweight dev tool that makes ML workflows and ML infra easier to reproduce.

That being said, we're open to collaborating with enterprises and helping them adopt dstack and accelerate AI research.  

#### How is dstack better than other tools?

The main value of dstack is in its lightweight-ness. You describe your
workflows as code and can run anywhere via a single CLI command.

dstack integrates with Git directly and provides a simple and developer-friendly CLI 
that can be used from your favourite IDE or terminal.

#### Didn't find your question above?

Join our [Slack chat](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ) and ask it there.