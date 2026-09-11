/** @jest-environment node */
import React from 'react';
import { Provider } from 'react-redux';
import { act, create, ReactTestRenderer } from 'react-test-renderer';
import { configureStore } from '@reduxjs/toolkit';

import { presetApi, useGetPresetQuery } from './preset';

jest.mock('api', () => ({
    API: {
        PRESET: { LIST: () => 'http://localhost/api/presets/list' },
        PROJECTS: {
            PRESETS_GET: (project: string) => `http://localhost/api/project/${project}/presets/get`,
            PRESETS_DELETE: (project: string) => `http://localhost/api/project/${project}/presets/delete`,
        },
    },
}));

jest.mock('App/slice', () => ({
    selectAuthToken: (state: { app: { authData?: { token?: string } } }) => state.app.authData?.token,
}));

const createStore = () =>
    configureStore({
        reducer: {
            app: (state = { authData: { token: 'viewer-a' as string | undefined } }, action) =>
                action.type === 'test/setToken' ? { authData: { token: action.payload } } : state,
            [presetApi.reducerPath]: presetApi.reducer,
        },
        middleware: (getDefaultMiddleware) => getDefaultMiddleware().concat(presetApi.middleware),
    });

const jsonResponse = (data: unknown, status = 200) =>
    new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

const flushUpdates = async () => {
    await act(async () => {
        await new Promise<void>((resolve) => setImmediate(resolve));
    });
};

describe('Preset viewer isolation', () => {
    let store: ReturnType<typeof createStore>;
    let rendered: ReactTestRenderer | undefined;
    let fetchMock: jest.SpyInstance;
    let requests: Request[];

    beforeEach(() => {
        store = createStore();
        requests = [];
        fetchMock = jest.spyOn(globalThis, 'fetch');
    });

    afterEach(() => {
        act(() => rendered?.unmount());
        rendered = undefined;
        store.dispatch(presetApi.util.resetApiState());
        fetchMock.mockRestore();
    });

    it('keeps list credentials out of the body and does not give guest queries the current account token', async () => {
        fetchMock.mockImplementation(async (input: Request) => {
            requests.push(input);
            const name = input.headers.get('Authorization') ?? 'public';
            return jsonResponse({ presets: [{ id: name, name, project_name: 'project', can_delete: name !== 'public' }] });
        });

        const member = await store
            .dispatch(presetApi.endpoints.getAllPresets.initiate({ scope: 'public', authToken: 'viewer-a' }))
            .unwrap();
        const guest = await store.dispatch(presetApi.endpoints.getAllPresets.initiate({ scope: 'public' })).unwrap();

        expect(member[0].can_delete).toBe(true);
        expect(guest[0].can_delete).toBe(false);
        expect(requests).toHaveLength(2);
        expect(requests[0].headers.get('Authorization')).toBe('Bearer viewer-a');
        expect(requests[1].headers.get('Authorization')).toBeNull();
        expect(await requests[0].json()).toEqual({ scope: 'public' });
        expect(await requests[1].json()).toEqual({ scope: 'public' });
    });

    it('never renders a cached private detail after switching accounts or signing out', async () => {
        let completeSecondRequest: ((response: Response) => void) | undefined;
        fetchMock.mockImplementation(async (input: Request) => {
            requests.push(input);
            const authorization = input.headers.get('Authorization');
            if (authorization === 'Bearer viewer-a') {
                return jsonResponse({ id: 'preset-id', name: 'Account A private preset', project_name: 'project' });
            }
            if (authorization === 'Bearer viewer-b') {
                return new Promise<Response>((resolve) => {
                    completeSecondRequest = resolve;
                });
            }
            return jsonResponse({ detail: 'Preset not found' }, 404);
        });

        const Detail = () => {
            const { currentData, error } = useGetPresetQuery({ project_name: 'project', id: 'preset-id' });
            return <span>{currentData?.name ?? (error ? 'Unavailable' : 'Loading')}</span>;
        };
        await act(async () => {
            rendered = create(
                <Provider store={store}>
                    <Detail />
                </Provider>,
            );
        });
        await flushUpdates();
        expect(rendered?.root.findByType('span').children).toEqual(['Account A private preset']);

        act(() => {
            store.dispatch({ type: 'test/setToken', payload: 'viewer-b' });
        });
        expect(rendered?.root.findByType('span').children).toEqual(['Loading']);
        await flushUpdates();
        expect(completeSecondRequest).toBeDefined();
        await act(async () => {
            completeSecondRequest?.(jsonResponse({ id: 'preset-id', name: 'Account B preset', project_name: 'project' }));
        });
        await flushUpdates();
        expect(rendered?.root.findByType('span').children).toEqual(['Account B preset']);

        act(() => {
            store.dispatch({ type: 'test/setToken', payload: undefined });
        });
        expect(rendered?.root.findByType('span').children).toEqual(['Loading']);
        await flushUpdates();
        expect(rendered?.root.findByType('span').children).toEqual(['Unavailable']);
        expect(requests.map((request) => request.headers.get('Authorization'))).toEqual([
            'Bearer viewer-a',
            'Bearer viewer-b',
            null,
        ]);
        expect(await requests[0].json()).toEqual({ name_or_id: 'preset-id' });
    });
});
