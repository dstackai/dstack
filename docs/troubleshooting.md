# Troubleshooting

This document outlines the best practices for troubleshooting issues when using `dstack`.

## Need help or have a question?

Have a questions about `dstack` or need help with using it yourself or with your team? Drop us a message 
in our [Slack channel](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ).

[![Slack](https://img.shields.io/badge/slack-join%20community-blueviolet?logo=slack&style=for-the-badge)](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)

## Report a bug

To resolve an issue as quickly as possible, it is best to report it directly to the [tracker](https://github.com/dstackai/dstack/issues). 
This is the most reliable method.

[![Slack](https://img.shields.io/badge/github-new%20issue-brightgreen?logo=github&style=for-the-badge)](https://github.com/dstackai/dstack/issues/new?assignees=&labels=bug&template=bug_report.yaml&title=%5BBug%5D%3A+)

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

## Request a feature

To request a feature, improvement, or integration with another tool, please create an issue directly in the
[tracker](https://github.com/dstackai/dstack/issues).

[![Slack](https://img.shields.io/badge/github-new%20issue-brightgreen?logo=github&style=for-the-badge)](https://github.com/dstackai/dstack/issues/new?assignees=&labels=feature&template=feature_request.yaml&title=%5BFeature%5D%3A+)

Provide details on your use case, what is missing or inconvenient, and a clear description of how you envision the proposed feature to function.