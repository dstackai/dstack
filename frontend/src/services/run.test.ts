/** @jest-environment node */
import { configureStore } from '@reduxjs/toolkit';

import { runApi } from './run';

jest.mock('api', () => ({
    API: {
        RUNS: { LIST: () => 'http://localhost/api/runs/list' },
    },
}));

const createStore = () =>
    configureStore({
        reducer: {
            app: (state = { authData: { token: 'token' } }) => state,
            [runApi.reducerPath]: runApi.reducer,
        },
        middleware: (getDefaultMiddleware) => getDefaultMiddleware().concat(runApi.middleware),
    });

// The latest run first. The runs 99 and 100, the last of the first page and the first of the second one, are submitted at the same time
const makeRuns = (count: number, modelRuns: number[]) =>
    Array.from({ length: count }, (_, index) => {
        const submittedAt = Date.UTC(2026, 11, 3, 9) - (index === 100 ? 99 : index) * 60000;

        return {
            id: `run-${String(index).padStart(4, '0')}`,
            project_name: 'exporter-proj',
            user: 'alice',
            submitted_at: new Date(submittedAt).toISOString(),
            status: 'running',
            run_spec: { run_name: `run-${index}` },
            service: modelRuns.includes(index)
                ? { model: { name: `model-${index}`, type: 'chat', base_url: 'https://gateway.example.com/exporter-proj' } }
                : null,
        } as IRun;
    });

describe('Models of runs', () => {
    let store: ReturnType<typeof createStore>;
    let fetchMock: jest.SpyInstance;
    let runs: IRun[];
    let requests: TRunsRequestParams[];

    // A page of the runs list, as the server pages it: after the run of the cursor,
    // which for runs submitted at the same time is the run with the next id
    const listRuns = ({ limit, prev_submitted_at, prev_run_id }: TRunsRequestParams) =>
        runs
            .filter(
                ({ id, submitted_at }) =>
                    !prev_submitted_at ||
                    submitted_at < prev_submitted_at ||
                    (submitted_at === prev_submitted_at && !!prev_run_id && id > prev_run_id),
            )
            .slice(0, limit);

    const getModelRuns = async (params: Pick<TRunsRequestParams, 'only_active'>) => {
        const models = await store.dispatch(runApi.endpoints.getModels.initiate(params)).unwrap();

        return models.map(({ run }) => run?.id);
    };

    beforeEach(() => {
        store = createStore();
        requests = [];
        fetchMock = jest.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
            const params = await (input as Request).json();

            requests.push(params);

            return new Response(JSON.stringify(listRuns(params)), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
            });
        });
    });

    afterEach(() => {
        store.dispatch(runApi.util.resetApiState());
        fetchMock.mockRestore();
    });

    test('reads the runs page by page, each page after the last run of the page before, until a page is not full', async () => {
        runs = makeRuns(250, [100, 249]);

        const page = { only_active: true, limit: 100, job_submissions_limit: 1 };

        expect(await getModelRuns({ only_active: true })).toEqual([runs[100].id, runs[249].id]);
        expect(requests).toEqual([
            page,
            { ...page, prev_submitted_at: runs[99].submitted_at, prev_run_id: runs[99].id },
            { ...page, prev_submitted_at: runs[199].submitted_at, prev_run_id: runs[199].id },
        ]);
    });

    test('reads every active run, and the latest 1,000 runs when not only the active ones are asked for', async () => {
        runs = makeRuns(1100, [999, 1000]);

        expect(await getModelRuns({ only_active: true })).toEqual([runs[999].id, runs[1000].id]);
        expect(await getModelRuns({})).toEqual([runs[999].id]);
    });
});
