/** @jest-environment node */
import React from 'react';
import { Provider } from 'react-redux';
import { act, create, ReactTestRenderer } from 'react-test-renderer';
import { configureStore } from '@reduxjs/toolkit';
import { QueryStatus } from '@reduxjs/toolkit/query';

import { importApi } from 'services/import';
import { projectApi } from 'services/project';
import { runApi } from 'services/run';

import { useModel } from './Details/hooks';
import { useProjectsImports } from './hooks';

let mockHasExports: boolean;

jest.mock('product', () => ({
    product: {
        get hasExports() {
            return mockHasExports;
        },
    },
}));

jest.mock('api', () => ({
    API: {
        PROJECTS: {
            LIST: () => 'http://localhost/api/projects/list',
            IMPORTS_LIST: (project: string) => `http://localhost/api/project/${project}/imports/list`,
        },
        RUNS: {
            LIST: () => 'http://localhost/api/runs/list',
        },
    },
}));

jest.mock('App/slice', () => ({ selectUserName: () => 'bob', selectUserData: () => null }));
jest.mock('hooks', () => ({ useAppSelector: (selector: () => unknown) => selector() }));

const QWEN = 'Qwen/Qwen3.6-27B-FP8';

// A run of exporter-proj that serves the model
const qwenRun = {
    id: 'run-id',
    project_name: 'exporter-proj',
    user: 'alice',
    submitted_at: '2026-12-03T09:02:00+00:00',
    status: 'running',
    run_spec: { run_name: 'qwen-service' },
    service: { model: { name: QWEN, type: 'chat', base_url: 'https://gateway.example.com/exporter-proj' } },
};

const createStore = () =>
    configureStore({
        reducer: {
            app: (state = { authData: { token: 'token' } }) => state,
            [projectApi.reducerPath]: projectApi.reducer,
            [importApi.reducerPath]: importApi.reducer,
            [runApi.reducerPath]: runApi.reducer,
        },
        middleware: (getDefaultMiddleware) =>
            getDefaultMiddleware().concat(projectApi.middleware, importApi.middleware, runApi.middleware),
    });

const jsonResponse = (data: unknown, status = 200) =>
    new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

describe('Models hooks', () => {
    let store: ReturnType<typeof createStore>;
    let rendered: ReactTestRenderer | undefined;
    let fetchMock: jest.SpyInstance;
    // The path of each request and, when it has one, its body
    let requests: [string, unknown?][];
    // What the server answers
    let runs: unknown[];
    let runsStatus: number;
    let importsStatuses: Record<string, number>;

    const renderHook = async <Result,>(useHook: () => Result) => {
        const result = {} as { current: Result };

        const Harness = () => {
            result.current = useHook();
            return null;
        };

        await act(async () => {
            rendered = create(
                <Provider store={store}>
                    <Harness />
                </Provider>,
            );
        });

        // One request follows another, like the import lists after the projects list. So wait until none has run for a while
        for (let idleTurns = 0; idleTurns < 3; idleTurns = isFetching() ? 0 : idleTurns + 1) {
            await act(async () => {
                await new Promise<void>((resolve) => setImmediate(resolve));
            });
        }

        return result;
    };

    const isFetching = () =>
        [projectApi, importApi, runApi].some(({ reducerPath }) =>
            Object.values(store.getState()[reducerPath].queries).some((query) => query?.status === QueryStatus.pending),
        );

    // Leaves the page. The cache then drops the answers that nothing uses any more, in a timer that this one follows
    const unmount = async () => {
        act(() => rendered?.unmount());
        rendered = undefined;

        await act(async () => {
            await new Promise<void>((resolve) => setTimeout(resolve));
        });
    };

    beforeEach(() => {
        store = createStore();
        requests = [];
        runs = [];
        runsStatus = 200;
        importsStatuses = {};
        fetchMock = jest.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
            const request = input as Request;
            const { pathname } = new URL(request.url);
            const loggedRequest: [string, unknown?] = [pathname];

            requests.push(loggedRequest);

            const body = await request.text();

            if (body) {
                loggedRequest.push(JSON.parse(body));
            }

            if (pathname === '/api/runs/list') {
                return jsonResponse(runsStatus === 200 ? runs : { detail: 'error' }, runsStatus);
            }

            if (pathname === '/api/projects/list') {
                return jsonResponse({
                    projects: [{ project_name: 'importer-proj' }, { project_name: 'importer2-proj' }],
                    total_count: 2,
                });
            }

            return jsonResponse({ imports: [], warnings: [] }, importsStatuses[pathname.split('/')[3]]);
        });
    });

    afterEach(async () => {
        await unmount();
        store.dispatch(projectApi.util.resetApiState());
        store.dispatch(importApi.util.resetApiState());
        store.dispatch(runApi.util.resetApiState());
        fetchMock.mockRestore();
    });

    test("requests the import list of each of the user's projects where the server has exports", async () => {
        mockHasExports = true;
        await renderHook(() => useProjectsImports());

        expect(requests).toEqual([
            ['/api/projects/list', { username: 'bob', return_total_count: true }],
            ['/api/project/importer-proj/imports/list'],
            ['/api/project/importer2-proj/imports/list'],
        ]);
    });

    test('requests nothing where the server has no exports', async () => {
        mockHasExports = false;
        await renderHook(() => useProjectsImports());

        expect(requests).toEqual([]);
    });

    test('leaves out an import list that failed, and keeps the others', async () => {
        mockHasExports = true;
        importsStatuses = { 'importer2-proj': 403 };

        const result = await renderHook(() => useProjectsImports());

        expect(result.current.projectsImports).toEqual([{ project_name: 'importer-proj', imports: [] }]);
    });

    test.each([
        ['is not found when the requests have answered without it', 200, true],
        ['is an error, and not "not found", when the runs request has failed', 500, false],
    ])('a model %s', async (name, status, isNotFound) => {
        mockHasExports = true;
        runsStatus = status;

        const result = await renderHook(() => useModel('exporter-proj', QWEN));

        expect(result.current.isLoading).toBe(false);
        expect(result.current.isNotFound).toBe(isNotFound);
        expect(!!result.current.error).toBe(!isNotFound);
    });

    test('a model that has started since a visit to its page is not "not found" in any render of the next visit', async () => {
        mockHasExports = true;

        const firstVisit = await renderHook(() => useModel('exporter-proj', QWEN));

        expect(firstVisit.current.isNotFound).toBe(true);

        await unmount();
        runs = [qwenRun];

        const isNotFoundInRenders: boolean[] = [];

        const nextVisit = await renderHook(() => {
            const result = useModel('exporter-proj', QWEN);

            isNotFoundInRenders.push(result.isNotFound);

            return result;
        });

        expect(isNotFoundInRenders).not.toContain(true);
        expect(nextVisit.current.model?.name).toBe(QWEN);
    });
});
