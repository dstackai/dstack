import type OpenAI from 'openai';

import { ROUTES } from 'routes';

import { addChunkToMessage, getCurlModelCode, getPythonModelCode, hasModelMetering } from './helpers';

import { IModelExtended } from '../List/types';
import { Message } from './types';

let mockHasBilling: boolean;

jest.mock('product', () => ({
    product: {
        get hasBilling() {
            return mockHasBilling;
        },
    },
}));

// exporter-proj runs the model, and importer-proj imports it
const model: IModelExtended = {
    name: 'Qwen/Qwen3.6-27B-FP8',
    project_name: 'exporter-proj',
    endpoints: [{ project_name: 'importer-proj', base_url: 'https://gateway.example.com/importer-proj' }],
};

const makeUser = (globalRole: TUserRole): IUser => ({
    id: 'bob-id',
    username: 'bob',
    global_role: globalRole,
    email: null,
    permissions: [],
    created_at: '2026-12-03T09:02:00+00:00',
    active: true,
});

const makeProject = (projectName: string, projectRole: TProjectRole) =>
    ({
        project_name: projectName,
        members: [{ user: { username: 'bob' }, project_role: projectRole }],
    }) as IProject;

beforeEach(() => {
    mockHasBilling = true;
});

describe('Model address', () => {
    test('keeps the slashes of the name and encodes the rest', () => {
        expect(ROUTES.MODELS.DETAILS.FORMAT('exporter-proj', 'Qwen/Qwen3.8-27B-FP8')).toBe(
            '/projects/exporter-proj/models/Qwen/Qwen3.8-27B-FP8',
        );
        expect(ROUTES.MODELS.DETAILS.FORMAT('exporter-proj', 'my model?/v1#x')).toBe(
            '/projects/exporter-proj/models/my%20model%3F/v1%23x',
        );
        expect(ROUTES.MODELS.DETAILS.METERING.FORMAT('exporter-proj', 'Qwen/Qwen3.8-27B-FP8')).toBe(
            '/projects/exporter-proj/models/Qwen/Qwen3.8-27B-FP8?tab=metering',
        );
    });

    test('a name with an empty part between slashes is encoded as a whole', () => {
        expect(ROUTES.MODELS.DETAILS.FORMAT('exporter-proj', 'a//b')).toBe('/projects/exporter-proj/models/a%2F%2Fb');
    });
});

describe('Model code', () => {
    test('is for the chosen project, else for the first of the projects that have the model', () => {
        const twoProjects = {
            ...model,
            endpoints: [
                ...model.endpoints,
                { project_name: 'importer2-proj', base_url: 'https://gateway.example.com/importer2-proj' },
            ],
        };

        expect(getPythonModelCode({ model: twoProjects })).toContain('base_url="https://gateway.example.com/importer-proj"');
        expect(getPythonModelCode({ model: twoProjects, projectName: 'importer2-proj' })).toContain(
            'base_url="https://gateway.example.com/importer2-proj"',
        );
        expect(getCurlModelCode({ model: twoProjects, projectName: 'importer2-proj' })).toContain(
            'curl https://gateway.example.com/importer2-proj/chat/completions ',
        );
    });

    test('quotes in the name of a model end neither the Python string nor the curl body', () => {
        const quotedModel = { ...model, name: `it's a "model"` };

        expect(getPythonModelCode({ model: quotedModel })).toContain(`model="it's a \\"model\\"",`);
        expect(getCurlModelCode({ model: quotedModel })).toContain(`"model": "it'\\''s a \\"model\\"",`);
    });
});

describe('Chat reply', () => {
    // A reply's stream, as an engine sends it: a delta in each chunk and, in the last chunk, why the stream ended
    const getReply = (chunks: [delta: object, finishReason?: string][]) =>
        chunks.reduce<Message>(
            (message, [delta, finishReason = null]) =>
                addChunkToMessage(message, {
                    choices: [{ index: 0, delta, finish_reason: finishReason }],
                } as OpenAI.Chat.Completions.ChatCompletionChunk),
            { role: 'assistant', content: '' },
        );

    test('an answer that starts with blank lines shows without them', () => {
        const reply = getReply([[{ reasoning_content: 'Hmm.' }], [{ content: '\n\n' }], [{ content: 'Paris.' }], [{}, 'stop']]);

        expect(reply.content).toBe('Paris.');
    });

    test('the answer of a model that does not think', () => {
        const reply = getReply([
            [{ role: 'assistant', content: '' }],
            [{ content: 'Par' }],
            [{ content: 'is.' }],
            [{}, 'stop'],
        ]);

        expect(reply).toEqual({ role: 'assistant', content: 'Paris.', thinking: '', finish_reason: 'stop' });
    });

    test.each(['reasoning_content', 'reasoning'])('the thinking in `%s`, and then the answer', (field) => {
        const reply = getReply([
            [{ role: 'assistant', content: null, [field]: 'The capital ' }],
            [{ content: null, [field]: 'is Paris.' }],
            [{ content: 'Paris.', [field]: null }],
            [{}, 'stop'],
        ]);

        expect(reply).toEqual({
            role: 'assistant',
            content: 'Paris.',
            thinking: 'The capital is Paris.',
            finish_reason: 'stop',
        });
    });

    test('a reply that the limit of tokens cut before its answer', () => {
        const reply = getReply([[{ reasoning_content: 'Five words: ' }], [{ reasoning_content: 'hello' }, 'length']]);

        expect(reply).toEqual({ role: 'assistant', content: '', thinking: 'Five words: hello', finish_reason: 'length' });
    });
});

describe('Model metering tab', () => {
    test('a global admin gets it', () => {
        expect(hasModelMetering(model, [], makeUser('admin'))).toBe(true);
    });

    test.each(['exporter-proj', 'importer-proj'])('an admin of %s gets it', (projectName) => {
        expect(hasModelMetering(model, [makeProject(projectName, 'admin')], makeUser('user'))).toBe(true);
    });

    test.each([
        ['exporter-proj', 'user'],
        ['importer-proj', 'manager'],
        ['other-proj', 'admin'],
    ] as const)('a member of %s with the %s role does not get it', (projectName, projectRole) => {
        expect(hasModelMetering(model, [makeProject(projectName, projectRole)], makeUser('user'))).toBe(false);
    });

    test('nobody gets it where the server has no metering', () => {
        mockHasBilling = false;

        expect(hasModelMetering(model, [makeProject('exporter-proj', 'admin')], makeUser('admin'))).toBe(false);
    });
});
