# Troubleshooting

This document outlines the best practices for troubleshooting issues when using `dstack`.

## Need help or have a question?

Have a questions about `dstack` or need help with using it yourself or with your team? Drop us a message 
in our [Slack channel](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ).

[Join our Slack](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ){ class="md-go-to-action secondary slack" }

## Something doesn't work?

To resolve an issue as quickly as possible, it is best to report it directly to the [tracker](https://github.com/dstackai/dstack/issues). 
This is the most reliable method.

[Report a bug](https://github.com/dstackai/dstack/issues/new?assignees=&labels=bug&template=bug_report.yaml&title=%5BBug%5D%3A+){ class="md-go-to-action secondary github" }

When creating an issue report, it is essential to include the following information:

1. The version of the CLI (obtained from running `dstack --version`), the operating system, 
   Python, and the versions of local Python libraries (`pip freeze` or `conda list`).
2. The source code for a minimal example that reproduces the issue.
3. The exact steps required to reproduce the issue.
4. The expected behavior.
5. The actual behavior, including the error message or exception traceback.
6. Logs, including:
    - If the run is local, the entire contents of `~/.dstack/tmp/runner/configs/<runner-id>/logs/<runner-id>`
    - If the run is remote, the logs from the corresponding cloud service, such as the `/dstack/runners/<bucket>` 
     CloudWatch group and the `<runner-id>` CloudWatch stream (within the configured AWS region).
7. Screenshots (if applicable).

Providing this information will help ensure that the issue can be resolved as efficiently as possible.

## Miss a feature?

To request a feature, improvement, or integration with another tool, please create an issue directly in the
[tracker](https://github.com/dstackai/dstack/issues).

[Request a feature](https://github.com/dstackai/dstack/issues/new?assignees=&labels=feature&template=feature_request.yaml&title=%5BFeature%5D%3A+){ class="md-go-to-action secondary github" }

Provide details on your use case, what is missing or inconvenient, and a clear description of how you envision the proposed feature to function.