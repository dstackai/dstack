---
title: Deploying LLMs with Python API
---

# Deploying LLMs with Python API

The [Python API](../docs/reference/api/python/index.md) of `dstack` can be used to run 
[tasks](../docs/guides/tasks.md) and [services](../docs/guides/services.md) programmatically.

Below is an example of a Streamlit app that uses `dstack`'s API to deploy a quantized version of Llama 2 to your cloud
with a simple click of a button.

![](images/python-api/dstack-python-api-streamlit-example.png){ width=800 }

!!! info "How does the API work?"
    If you're familiar with Docker's Python SDK, you'll find dstack's Python API quite similar, except that it runs your
    workload in the cloud.

    To get started, create an instance of `dstack.Client` and use its methods to submit and manage runs.

    With `dstack.Client`, you can run [tasks](../docs/guides/tasks.md) and [services](../docs/guides/services.md). Running a task allows you to programmatically access its ports and
    forward traffic to your local machine. For example, if you run an LLM as a task, you can access it on localhost.

    For more details on the Python API, please refer to its [reference](../docs/docs/reference/api/python/index.md).

## Prerequisites

Before you can use `dstack` Python API, ensure you have installed the `dstack` package, 
started a `dstack` server with [configured clouds](../../docs/docs/guides/clouds.md).
    
```shell
pip install "dstack[all]>=0.11.2rc2"
dstack start
```

## Run the app

First, clone the repository with `dstack-examples`.

```shell
git clone https://github.com/dstackai/dstack-examples
cd dstack-examples
```

Second, install the requirements, and run the app:

```
pip install -r streamlit-llama/requirements.txt
streamlit run streamlit-llama/app.py
```

That's it! Now you can choose a model (e.g., 13B or 70B) and click the `Deploy` button.
Once the LLM is up, you can access it at `localhost`.

## Code walkthrough

For the complete code, 
refer to the [full version](https://github.com/dstackai/dstack-examples/blob/main/streamlit-llama/app.py).

First, we initialize the `dstack.Client`:

```python
if len(st.session_state) == 0:
    st.session_state.client = dstack.Client.from_config(".")
```

Then, we prompt the user to choose an LLM for deployment.

```python
def trigger_llm_deployment():
    st.session_state.deploying = True
    st.session_state.error = None

with st.sidebar:
    model_id = st.selectbox("Choose an LLM to deploy",
                            ("TheBloke/Llama-2-13B-chat-GPTQ",
                             "TheBloke/Llama-2-70B-chat-GPTQ",),
                            disabled=st.session_state.deploying or st.session_state.deployed)
    if not st.session_state.deploying:
        st.button("Deploy", on_click=trigger_llm_deployment, type="primary")
```

Prepare a `dstack` task and resource requirements based on the selected model.

```python
def get_configuration():
    return dstack.Task(
        image="ghcr.io/huggingface/text-generation-inference:latest",
        env={"MODEL_ID": model_id},
        commands=[
            "text-generation-launcher --trust-remote-code --quantize gptq",
        ],
        ports=["8080:80"],
    )


def get_resources():
    if model_id == "TheBloke/Llama-2-13B-chat-GPTQ":
        gpu_memory = "20GB"
    elif model_id == "TheBloke/Llama-2-70B-chat-GPTQ":
        gpu_memory = "40GB"
    return dstack.Resources(gpu=dstack.GPU(memory=gpu_memory))
```

If the user clicks `Deploy`, we submit the task using `runs.submit()` on `dstack.Client`. Then, we use the `attach()` 
method on `dstack.Run`. This method waits for the task to start, forwarding the port to `localhost`.

Finally, we wait until `http://localhost:8080/health` returns `200`.

```python
def wait_for_ok_status(url):
    while True:
        time.sleep(0.5)
        try:
            r = requests.get(url)
            if r.status_code == 200:
                break
        except Exception:
            pass

if st.session_state.deploying:
    with st.sidebar:
        with st.status("Deploying the LLM...", expanded=True) as status:
            st.write("Provisioning...")
            try:
                run = st.session_state.client.runs.submit(configuration=get_configuration(), run_name=run_name,
                                                          resources=get_resources())
                st.session_state.run = run
                st.write("Attaching to the LLM...")
                st.session_state.run.attach()
                wait_for_ok_status("http://localhost:8080/health")
                status.update(label="The LLM is ready!", state="complete", expanded=False)
                st.session_state.deploying = False
                st.session_state.deployed = True
            except Exception as e:
                st.session_state.error = str(e)
                st.session_state.deploying = False
                st.experimental_rerun()
```

If an error occurs, we display it. Additionally, we provide a button to undeploy the model using the `stop()` method on `dstack.Run`.

```python
def trigger_llm_undeployment():
    st.session_state.run.stop()
    st.session_state.deploying = False
    st.session_state.deployed = False
    st.session_state.run = None

with st.sidebar:
    if st.session_state.error:
        st.error(st.session_state)
        
    if st.session_state.deployed:
        st.button("Undeploy", type="primary", key="stop", on_click=trigger_llm_undeployment)
```

!!! info "Source code"
    The complete, ready-to-run code is available in [dstackai/dstack-examples](https://github.com/dstackai/dstack-examples).