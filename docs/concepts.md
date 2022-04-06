# Concepts

### 🧬 Workflow

Typical data and training pipelines consist of multiple steps. These steps may include loading data,
preparing data, training, validating, testing a model, etc. In dstack, each of these steps is called a `Workflow`.
Learn more on how to [define workflows](workflows.md).

### 🏃‍♀️ Run

Once you run a `Workflow`, the running instance of this workflow is called a `Run`. All `Jobs` created by the
`Provider` are linked to this `Run`.

### 🧩 Provider

A `Provider` is a program that materializes a `Workflow` into actual `Jobs` that 
process and output data according to the `Workflow` parameters.

### ⚙️ Job

When you run a `Workflow`, the `Provider` creates the actual `Jobs` that run this `Workflow`.

Every `Job` is associated with a repo with the sources, a Docker image, commands, exposed ports, an ID of the primary `Job` (in
case there should be communication between `Jobs`), the input `Artifacts` (e.g. from other runs), 
the hardware requirements (e.g. the number or a name of GPU, memory, etc.), and finally the output `Artifacts`.

### 📦 Artifact

Every `Job` may produce output `Artifacts`. When a `Job` is running, dstack stores the output `Artifacts` for 
every `Job` in real-time.

If your `Job` depends on some another `Job`, all output `Artifacts` of that other `Job` will be
mounted as input `Artifacts` to your `Job`.

### 🏷 Tags

It's possible to assign a `Tag` to any successful `Run` to reuse its `Artifacts` in other `Workflows`. 
By using `Tags`, it's possible to version data and models, and reuse it within the team or across.

### 🤖 Runner

A `Runner` is a machine that runs `Jobs`. `Runners` are provisioned by dstack on-demand from the configured
`Computing Vendors` (such as AWS, GCP, Azure, and others.) As an alternative to on-demand `Runners`, it's also possible 
to use your own hardware as `Runners` (this is called self-hosted `Runners`). 
Learn more on how to [set up runners](runners.md).