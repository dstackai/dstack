# Troubleshooting

This document outlines the best practices for troubleshooting issues when using `dstack`.

## Need help or have a question?

Have a questions about `dstack` or need help with using it yourself or with your team? Drop us a message 
in our [Slack channel](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ).

[Join our Slack](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ){ class="md-go-to-action primary slack" }

## Something doesn't work?

To resolve an issue as quickly as possible, it is best to report it directly to the [issue tracker](https://github.com/dstackai/dstack/issues). 
This is the most reliable method.

[Report a bug](https://github.com/dstackai/dstack/issues/new?assignees=&labels=bug&template=bug_report.yaml&title=%5BBug%5D%3A+){ class="md-go-to-action secondary github" }

When creating an issue report, it is essential to include the following information:

1. The version of the CLI (obtained from running `dstack --version`), the operating system, 
   Python, and the versions of local Python libraries (`pip freeze` or `conda list`).
2. The source code for a minimal example that reproduces the issue.
3. The exact steps required to reproduce the issue.
4. The expected behavior.
5. The actual behavior, including the error message or exception traceback.
6. The logs, which can be found in the corresponding location depending on where the workflow was run:
    - For local runs, the logs are stored in the `~/.dstack/tmp/runner/configs/<runner-id>/logs/<runner-id>` text file.
    - For remote AWS runs, the logs are stored in the `/dstack/runners/<bucket>` 
      CloudWatch group in the `<runner-id>` CloudWatch stream (within the configured AWS region).
    - For remote GCP runs, the logs are stored under the `projects/dstack/logs/dstack-runners-<bucket>-<runner-id>` log name.
      To filter out the logs of a particular run, type `dstack-runners <run-name>` into the Logs Explorer search field.

7. Screenshots (if applicable).

Providing this information will help ensure that the issue can be resolved as efficiently as possible.

## Miss a feature?

To request a feature, improvement, or integration with another tool, please create an issue directly in the
[tracker](https://github.com/dstackai/dstack/issues).

[Request a feature](https://github.com/dstackai/dstack/issues/new?assignees=&labels=feature&template=feature_request.yaml&title=%5BFeature%5D%3A+){ class="md-go-to-action secondary github" }

Provide details on your use case, what is missing or inconvenient, and a clear description of how you envision the proposed feature to function.