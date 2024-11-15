import { getModelGateway } from '../helpers';

import { IModelExtended } from '../List/types';

export const getPythonModelCode = ({ model, token }: { model?: IModelExtended | null; token?: string }) => {
    return `from openai import OpenAI
client = OpenAI(
    api_key="${token}"
    base_url="${getModelGateway(model?.base_url ?? '')}"
)

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

export const getCurlModelCode = ({ model, token }: { model?: IModelExtended | null; token?: string }) => {
    return `curl ${getModelGateway(model?.base_url ?? '')} \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${token}" \\
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
