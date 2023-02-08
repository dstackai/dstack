---
name: Bug report
about: Report a bug
title: ''
labels: bug
assignees: ''

---

**Describe the bug**
A clear and concise description of what the bug is.

**Version**
 - The `dstack` CLI version
 - The operational system version
 - The Python version
- (Optional) Other Python packages versions (`pip freeze` or `conda list`)

**Minimal example**
Attach the source code of a minimal example that can be used to reproduce the issue.

**Steps to reproduce**
Write the exact steps to reproduce the issue.

**Expected behavior**
Write the actual behavior, including the exact error messages or exception tracebacks.

**Logs**
Attach all `dstack` logs that correspond to the bug.

If the run is local, attach the entire contents of `~/.dstack/tmp/runner/configs/<runner-id>/logs/<runner-id>`.

If the run is remote, attach the logs from the corresponding cloud. For example, if it's AWS, the logs can be found in the `/dstack/runners/<bucket>` CloudWatch group and the `<runner-id>`  CloudWatch stream (within the configured AWS region).

**Screenshots**
Attach screenshots (if any).

**Additional context**
Add any other context about the problem here.
