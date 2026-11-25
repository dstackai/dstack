import type OpenAI from 'openai';
import { product } from 'product';

import { GlobalUserRole, ProjectUserRole } from 'types';

import { getProjectRoleByUserName } from 'pages/Project/utils';

import { getModelGateway } from '../helpers';

import { IModelExtended } from '../List/types';
import { Message } from './types';

// The most tokens of a reply in the chat and in the code. A thinking model's thinking counts too
export const MAX_TOKENS = 4096;

/**
 * The URL through which the user accesses the model, for the chat and the code: the model endpoint of `projectName`,
 * else the first one, which is of the model's own project for its members, else of the first of the user's projects
 * that imports it.
 */
export const getModelUrl = (model?: IModelExtended, projectName?: IProject['project_name']) => {
    const endpoint = model?.endpoints.find(({ project_name }) => project_name === projectName) ?? model?.endpoints[0];

    return getModelGateway(endpoint?.base_url);
};

type TChatCompletionChunk = OpenAI.Chat.Completions.ChatCompletionChunk;

// An engine with a reasoning parser streams a model's thinking apart from its answer:
// in `reasoning_content`, or in `reasoning` with some engines. The OpenAI client has neither field
type TChatCompletionDelta = TChatCompletionChunk['choices'][number]['delta'] & {
    reasoning_content?: string | null;
    reasoning?: string | null;
};

/**
 * Adds a chunk of a reply's stream to the reply: its answer, its thinking and, at the end, why the stream ended.
 */
export const addChunkToMessage = (message: Message, chunk: TChatCompletionChunk): Message => {
    const choice = chunk.choices[0];
    const delta: TChatCompletionDelta | undefined = choice?.delta;

    return {
        role: delta?.role ?? message.role,
        // A thinking model's answer starts with blank lines, which would show as a gap above it
        content: (message.content + (delta?.content ?? '')).trimStart(),
        thinking: (message.thinking ?? '') + (delta?.reasoning_content ?? delta?.reasoning ?? ''),
        finish_reason: choice?.finish_reason ?? message.finish_reason,
    };
};

/**
 * An imported model's name comes from another project and can be any string, so the code has it as a JSON string,
 * which is a Python string too.
 */
const getModelNameLiteral = (model?: IModelExtended) => JSON.stringify(model?.name ?? '');

type TModelCodeParams = {
    model?: IModelExtended;
    // The project whose model endpoint the code uses
    projectName?: IProject['project_name'];
    token?: string;
};

export const getPythonModelCode = ({ model, projectName, token }: TModelCodeParams) => {
    return `from openai import OpenAI
client = OpenAI(
    api_key="${token}",
    base_url="${getModelUrl(model, projectName)}"
)

response = client.chat.completions.create(
    model=${getModelNameLiteral(model)},
    messages=[
        {
            "role": "user",
            "content": "Hello world",
        },
    ],
    stream=True,
    max_tokens=${MAX_TOKENS},
)`;
};

export const getCurlModelCode = ({ model, projectName, token }: TModelCodeParams) => {
    const url = getModelUrl(model, projectName).replace(/\/$/, '') + '/chat/completions';
    // The body is in single quotes, which a single quote of the name would end
    const modelName = getModelNameLiteral(model).replace(/'/g, `'\\''`);

    return `curl ${url} \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${token}" \\
  -d '{
  "model": ${modelName},
  "messages": [
    {
      "role": "user",
      "content": "Hello world"
    }
  ],
  "stream": true,
  "max_tokens": ${MAX_TOKENS}
}'`;
};

/**
 * The Metering tab is for global admins and for the admins of the project that runs the model
 * or of a project that imports it, where the server has the metering API.
 */
export const hasModelMetering = (model: IModelExtended, projects: IProject[], user: IUser | null): boolean => {
    if (!product.hasBilling || !user) {
        return false;
    }

    if (user.global_role === GlobalUserRole.ADMIN) {
        return true;
    }

    const modelProjectNames = [model.project_name, ...model.endpoints.map(({ project_name }) => project_name)];

    return projects.some(
        (project) =>
            modelProjectNames.includes(project.project_name) &&
            getProjectRoleByUserName(project, user.username) === ProjectUserRole.ADMIN,
    );
};
