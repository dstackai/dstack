import { getModelGateway } from '../helpers';

import { IModelExtended } from '../List/types';

export const getPythonModelCode = ({ model, token }: { model?: IModelExtended | null; token?: string }) => {
    return `from openai import OpenAI
client = OpenAI(
    api_key="${token}",
    base_url="${getModelGateway(model?.base_url ?? '')}"
)

response = client.chat.completions.create(
    model="${model?.name ?? ''}",
    messages=[
        {
            "role": "user",
            "content": "Hello world",
        },
    ],
    stream=True,
    max_tokens=512,
)`;
};

export const getCurlModelCode = ({ model, token }: { model?: IModelExtended | null; token?: string }) => {
    const url = getModelGateway(model?.base_url ?? '').replace(/\/$/, '') + '/chat/completions';
    return `curl ${url} \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${token}" \\
  -d '{
  "model": "${model?.name ?? ''}",
  "messages": [
    {
      "role": "user",
      "content": "Hello world"
    }
  ],
  "stream": true,
  "max_tokens": 512
}'`;
};
