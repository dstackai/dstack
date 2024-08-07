# Chat UI

This example walks you through setting up [Chat UI](https://github.com/huggingface/chat-ui) locally
to chat with an LLM deployed using `dstack`.

### Clone the repo

```shell
git clone https://github.com/huggingface/chat-ui
cd chat-ui
```

### Run local MongoDB

```shell
docker run -d -p 27017:27017 --name mongo-chatui mongo:latest
```

### Create `.env.local`

```shell
MONGODB_URL=mongodb://localhost:27017

MODELS=`[
   {
      "name": "<model name>",
      "displayName": "My model",
      "endpoints": [
        {
         "type": "openai",
         "baseURL" : "https://gateway.<gateway domain>",
         "apiKey": "<dstack token>"
        }
      ]
  }
]`
```

Replace `<gateway domain>` with your `dstack` gateway's domain (e.g. `<dstack project>.sky.dstack.ai` if you are using [dstack Sky](https://sky.dstack.ai)).

Replace `<dstack token>` with your `dstack` user's token.

Replace `<model name>` with the name of the deployed mode,

### Run Chat UI

```shell
npm run dev
```

Now you can conveniently chat with your model! 🤗

![](images/dstack-chat-ui-llama3.png)