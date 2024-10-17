import { IModelExtended } from '../List/types';

export const getPythonModelCode = (model?: IModelExtended | null) => {
    return `from openai import OpenAI
client = OpenAI()

response = client.chat.completions.create(
  model="${model?.name ?? ''}",
  messages=[],
  stream=True,
  max_tokens=512,
  response_format={
    "type": "text"
  }
)`;
};

export const getCurlModelCode = (model?: IModelExtended | null) => {
    return `curl https://api.openai.com/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer $OPENAI_API_KEY" \\
  -d '{
  "model": "${model?.name ?? ''}",
  "messages": [],
  "stream": true,
  "max_tokens": 512,
  "response_format": {
    "type": "text"
  }
}'`;
};
