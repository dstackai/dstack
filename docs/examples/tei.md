# Text Embeddings Inference

This example demonstrates how to use [TEI](https://github.com/huggingface/text-embeddings-inference) with `dstack`'s
[services](../docs/concepts/services.md) to deploy embeddings.

## Define the configuration

To deploy a text embeddings model as a service using TEI, define the following configuration file:

<div editor-title="deployment/tae/serve.dstack.yml"> 

```yaml
type: service

image: ghcr.io/huggingface/text-embeddings-inference:latest
env:
  - MODEL_ID=thenlper/gte-base
commands: 
  - text-embeddings-router --port 80
port: 80
```

</div>

## Run the configuration

!!! warning "Gateway"
    Before running a service, ensure that you have configured a [gateway](../docs/concepts/services.md#set-up-a-gateway).
    If you're using dstack Cloud, the default gateway is configured automatically for you.

<div class="termy">

```shell
$ dstack run . -f deployment/tae/serve.dstack.yml --gpu 24GB
```

</div>

## Access the endpoint
    
Once the service is up, you can query it at 
`https://<run name>.<gatewy domain>` (using the domain set up for the gateway):

<div class="termy">

```shell
$ curl https://yellow-cat-1.example.com \
    -X POST \
    -H 'Content-Type: application/json' \
    -d '{"inputs":"What is Deep Learning?"}'

[[0.010704354,-0.033910684,0.004793657,-0.0042832214,0.07551489,0.028702762,0.03985837,0.021956133,...]]
```

</div>

!!! info "Hugging Face Hub token"

    To use a model with gated access, ensure configuring the `HUGGING_FACE_HUB_TOKEN` environment variable 
    (with [`--env`](../docs/reference/cli/index.md#dstack-run) in `dstack run` or 
    using [`env`](../docs/reference/dstack.yml.md#service) in the configuration file).
    
    <div class="termy">
    
    ```shell
    $ dstack run . -f text-embeddings-inference/serve.dstack.yml \ 
        --env HUGGING_FACE_HUB_TOKEN=&lt;token&gt; \
        --gpu 24GB
    ```
    </div>

[//]: # (## Use embeddings API)

[//]: # ()
[//]: # (Here's an example of how text embeddings deployed with TEI can be used from [`langchain`]&#40;https://python.langchain.com/docs/get_started/introduction&#41; to build a simple RAG pipeline.)

[//]: # (As the first step of the pipeline, we define an in-memory vector store with a collection of texts and their embeddings.)

[//]: # (Then we use it to retrieve the most relevant documents given a query.)

[//]: # ()
[//]: # (<div editor-title="text-embeddings-inference/main.py"> )

[//]: # ()
[//]: # (```python)

[//]: # (from langchain.embeddings import HuggingFaceInferenceAPIEmbeddings)

[//]: # (from langchain.vectorstores.docarray import DocArrayInMemorySearch)

[//]: # (from langchain_core.runnables import RunnableParallel, RunnablePassthrough)

[//]: # ()
[//]: # (# Specify your service url)

[//]: # (EMBEDDINGS_URL = "https://tall-octopus-1.example.com")

[//]: # ()
[//]: # (embedding=HuggingFaceInferenceAPIEmbeddings&#40;)

[//]: # (    api_url=EMBEDDINGS_URL,)

[//]: # (    api_key="", # No api key required)

[//]: # (&#41;)

[//]: # (texts = [)

[//]: # (    "The earliest known name for Great Britain is Albion &#40;Greek: Ἀλβιών&#41; or insula Albionum",)

[//]: # (    "Human footprints have been found from over 800,000 years ago in Norfolk.",)

[//]: # (    # ...)

[//]: # (])

[//]: # (vectorstore = DocArrayInMemorySearch.from_texts&#40;texts, embedding&#41;)

[//]: # (retriever = vectorstore.as_retriever&#40;search_kwargs={"k": 1}&#41;)

[//]: # (setup_and_retrieval = RunnableParallel&#40;)

[//]: # (    {"context": retriever, "question": RunnablePassthrough&#40;&#41;})

[//]: # (&#41;)

[//]: # (print&#40;setup_and_retrieval.invoke&#40;"How was Great Britain called before?"&#41;&#41;)

[//]: # (# {)

[//]: # (#     'context':[Document&#40;page_content='The earliest known name for Great Britain is Albion &#40;Greek: Ἀλβιών&#41; or insula Albionum'&#41;],)

[//]: # (#     'question': 'How was Great Britain called before?')

[//]: # (# })

[//]: # (```)

[//]: # ()
[//]: # (</div>)

[//]: # ()
[//]: # (The result can then be passed as a context to the LLM's prompt.)

[//]: # (We deploy the LLM using Services and Text Generation Inference &#40;TGI&#41;.)

[//]: # (See [our guide on TGI]&#40;./tgi.md&#41; for more details.)

[//]: # ()
[//]: # (<div editor-title="text-embeddings-inference/main.py">)

[//]: # ()
[//]: # ()
[//]: # (```python)

[//]: # ()
[//]: # (from langchain.prompts import PromptTemplate)

[//]: # (from langchain_core.output_parsers import StrOutputParser)

[//]: # (from langchain.llms.huggingface_text_gen_inference import &#40;)

[//]: # (    HuggingFaceTextGenInference)

[//]: # (&#41;)

[//]: # ()
[//]: # (# Specify your service url)

[//]: # (INFERENCE_URL = "https://shy-elephant-1.examples.cloud.dstack.ai")

[//]: # ()
[//]: # (template = """)

[//]: # (<s>[INST] Answer the question using the following context:)

[//]: # ({context})

[//]: # ()
[//]: # (Question: {question} [/INST])

[//]: # (""")

[//]: # (prompt = PromptTemplate.from_template&#40;template&#41;)

[//]: # (model = HuggingFaceTextGenInference&#40;)

[//]: # (    inference_server_url=INFERENCE_URL,)

[//]: # (    max_new_tokens=500,)

[//]: # (&#41;)

[//]: # (output_parser = StrOutputParser&#40;&#41;)

[//]: # ()
[//]: # (chain = setup_and_retrieval | prompt | model | output_parser)

[//]: # ()
[//]: # (print&#40;chain.invoke&#40;"How was Great Britain called before?"&#41;&#41;)

[//]: # (# Before its modern name, Great Britain was known as Albion.)

[//]: # (# This name is derived from the Latin term 'insula Albionum'.)

[//]: # (```)

[//]: # ()
[//]: # (</div>)

[//]: # ()
[//]: # (For searching over many texts quickly, consider using a vector database such as)

[//]: # ([Weaviate]&#40;https://weaviate.io/&#41; or [Pinecone]&#40;https://www.pinecone.io/&#41;.)

[//]: # (Take a look at [our guide on using Weaviate with LlamaIndex]&#40;llama-index.md&#41;.)

[//]: # ()
[//]: # (!!! info "Troubleshooting")

[//]: # (    You may get `batch size > maximum allowed batch size 32` when passing more than 32 texts to TEI.)

[//]: # (    `HuggingFaceInferenceAPIEmbeddings` does not allow you to specify the batch size, so)

[//]: # (    you'll have to split your texts into batches and add them to vector store via `vectorstore.add_texts&#40;&#41;`.)

## Source code

The complete, ready-to-run code is available in [`dstackai/dstack-examples`](https://github.com/dstackai/dstack-examples).

## What's next?

1. Check the [Text Generation Inference](tgi.md) and [vLLM](vllm.md) examples
2. Read about [services](../docs/concepts/services.md)
3. Browse all [examples](index.md)
4. Join the [Discord server](https://discord.gg/u8SmfwPpMd)