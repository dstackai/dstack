# Serving text embeddings with TEI

This example demonstrates how to deploy a text embeddings model as an API using [Services](../docs/guides/services.md) and [Text Embeddings Inference (TEI)](https://github.com/huggingface/text-embeddings-inference), an open-source toolkit by Hugging Face for efficient deployment and serving of open source text embeddings models.

## Define the configuration

To deploy a text embeddings model as a service using TEI, define the following configuration file:


<div editor-title="text-embeddings-inference/serve.dstack.yml"> 

```yaml
type: service

image: ghcr.io/huggingface/text-embeddings-inference:latest

env:
  - MODEL_ID=thenlper/gte-base

port: 8000

commands: 
  - text-embeddings-router --hostname 0.0.0.0 --port 8000

```

</div>

## Run the configuration

!!! warning "Gateway"
    Before running a service, ensure that you have configured a [gateway](../docs/guides/services.md#set-up-a-gateway).
    If you're using dstack Cloud, the dstack gateway is configured automatically for you.

<div class="termy">

```shell
$ dstack run . -f text-embeddings-inference/embeddings.dstack.yml --gpu 24GB
```

</div>

!!! info "Endpoint URL"
    Once the service is deployed, its endpoint will be available at 
    `https://<run-name>.<domain-name>` (using the domain set up for the gateway).

    If you wish to customize the run name, you can use the `-n` argument with the `dstack run` command.

Once the service is up, you can query it:

<div class="termy">

```shell
$ curl https://yellow-cat-1.examples.cloud.dstack.ai \
    -X POST \
    -H 'Content-Type: application/json' \
    -d '{"inputs":"What is Deep Learning?"}'

[[0.010704354,-0.033910684,0.004793657,-0.0042832214,0.07551489,0.028702762,0.03985837,0.021956133,...]]
```

</div>

!!! info "Hugging Face Hub token"

    To use a model with gated access, ensure configuring the `HUGGING_FACE_HUB_TOKEN` environment variable 
    (with [`--env`](../docs/reference/cli/index.md#dstack-run) in `dstack run` or 
    using [`env`](../docs/reference/dstack.yml/service.md#env) in the configuration file).
    
    <div class="termy">
    
    ```shell
    $ dstack run . -f text-embeddings-inference/serve.dstack.yml \ 
        --env HUGGING_FACE_HUB_TOKEN=&lt;token&gt; \
        --gpu 24GB
    ```
    </div>

## Use embeddings API

Here's an example of how text embeddings deployed with TEI can be used from [`langchain`](https://python.langchain.com/docs/get_started/introduction) to build a simple RAG pipeline.
As the first step of the pipeline, we define an in-memory vector store with a collection of texts and their embeddings.
Then we use it to retrieve the most relevant documents given a query.

<div editor-title="text-embeddings-inference/main.py"> 

```python
from langchain.embeddings import HuggingFaceInferenceAPIEmbeddings
from langchain.vectorstores.docarray import DocArrayInMemorySearch
from langchain_core.runnables import RunnableParallel, RunnablePassthrough

# Specify your service url
EMBEDDINGS_URL = "https://tall-octopus-1.examples.cloud.dstack.ai"

embedding=HuggingFaceInferenceAPIEmbeddings(
    api_url=EMBEDDINGS_URL,
    api_key="", # No api key required
)
texts = [
    "The earliest known name for Great Britain is Albion (Greek: Ἀλβιών) or insula Albionum",
    "Human footprints have been found from over 800,000 years ago in Norfolk.",
    # ...
]
vectorstore = DocArrayInMemorySearch.from_texts(texts, embedding)
retriever = vectorstore.as_retriever(search_kwargs={"k": 1})
setup_and_retrieval = RunnableParallel(
    {"context": retriever, "question": RunnablePassthrough()}
)
print(setup_and_retrieval.invoke("How was Great Britain called before?"))
# {
#     'context':[Document(page_content='The earliest known name for Great Britain is Albion (Greek: Ἀλβιών) or insula Albionum')],
#     'question': 'How was Great Britain called before?'
# }
```

</div>

The result can then be passed as a context to the LLM's prompt.
We deploy the LLM using Services and Text Generation Inference (TGI).
See [our guide on TGI](./tgi.md) for more details.

<div editor-title="text-embeddings-inference/main.py">


```python

from langchain.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain.llms.huggingface_text_gen_inference import (
    HuggingFaceTextGenInference
)

# Specify your service url
INFERENCE_URL = "https://shy-elephant-1.examples.cloud.dstack.ai"

template = """
<s>[INST] Answer the question using the following context:
{context}

Question: {question} [/INST]
"""
prompt = PromptTemplate.from_template(template)
model = HuggingFaceTextGenInference(
    inference_server_url=INFERENCE_URL,
    max_new_tokens=500,
)
output_parser = StrOutputParser()

chain = setup_and_retrieval | prompt | model | output_parser

print(chain.invoke("How was Great Britain called before?"))
# Before its modern name, Great Britain was known as Albion.
# This name is derived from the Latin term 'insula Albionum'.
```

</div>

For searching over many texts quickly, consider using a vector database such as
[Weaviate](https://weaviate.io/) or [Pinecone](https://www.pinecone.io/).
Take a look at [our guide on using Weaviate with LlamaIndex](llama-index.md).

!!! info "Troubleshooting"
    You may get `batch size > maximum allowed batch size 32` when passing more than 32 texts to TEI.
    `HuggingFaceInferenceAPIEmbeddings` does not allow you to specify the batch size, so
    you'll have to split your texts into batches and add them to vector store via `vectorstore.add_texts()`.

!!! info "Source code"
    The complete, ready-to-run code is available in [dstackai/dstack-examples](https://github.com/dstackai/dstack-examples).