import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

import { getExtendedModelFromRun } from '../libs/run';

import { IModelExtended, TModelsRequestParams } from '../pages/Models/List/types';

// The largest page of the runs list
const RUNS_PAGE_LIMIT = 100;

// How many of the latest runs are read for the models that no active run has
const MODELS_LATEST_RUNS_LIMIT = 1000;

const reduceInvalidateTagsFromRunNames = (names: Array<string>) => {
    return names.reduce((accumulator, runName: string) => {
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-ignore
        accumulator.push({ type: 'Runs', id: runName });
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-ignore
        accumulator.push({ type: 'AllRuns', id: runName });

        return accumulator;
    }, []);
};

export const runApi = createApi({
    reducerPath: 'runApi',
    refetchOnMountOrArgChange: true,
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Runs', 'Models', 'Metrics'],

    endpoints: (builder) => ({
        getRuns: builder.query<IRun[], TRunsRequestParams>({
            query: (body = {}) => {
                return {
                    url: API.RUNS.LIST(),
                    method: 'POST',
                    body,
                };
            },

            providesTags: (result) =>
                result ? [...result.map(({ id }) => ({ type: 'Runs' as const, id: id })), 'Runs'] : ['Runs'],
        }),

        getRun: builder.query<IRun | undefined, { project_name: string; id: string }>({
            query: ({ project_name, ...body }) => {
                return {
                    url: API.PROJECTS.RUN_DETAILS(project_name ?? ''),
                    method: 'POST',
                    body,
                };
            },

            providesTags: (result) => (result ? [{ type: 'Runs' as const, id: result?.id }] : []),
        }),

        applyRun: builder.mutation<{ id: string; project_name: string }, TRunApplyRequestParams>({
            query: ({ project_name, ...body }) => {
                return {
                    url: API.PROJECTS.RUNS_APPLY(project_name ?? ''),
                    method: 'POST',
                    body,
                };
            },

            // providesTags: (result) => (result ? [{ type: 'Runs' as const, id: result?.id }] : []),
        }),

        stopRuns: builder.mutation<void, TStopRunsRequestParams>({
            query: ({ project_name, ...body }) => ({
                url: API.PROJECTS.RUNS_STOP(project_name),
                method: 'POST',
                body,
            }),

            invalidatesTags: (result, error, params) => reduceInvalidateTagsFromRunNames(params.runs_names),
        }),

        deleteRuns: builder.mutation<void, TDeleteRunsRequestParams>({
            query: ({ project_name, ...body }) => ({
                url: API.PROJECTS.RUNS_DELETE(project_name),
                method: 'POST',
                body,
            }),

            invalidatesTags: (result, error, params) => reduceInvalidateTagsFromRunNames(params.runs_names),

            async onQueryStarted({ runs_names, project_name }, { dispatch, queryFulfilled }) {
                const patchGetRunResult = dispatch(
                    runApi.util.updateQueryData('getRuns', { project_name }, (draftRuns) => {
                        runs_names.forEach((runName) => {
                            const index = draftRuns.findIndex((run) => {
                                return run.run_spec.run_name === runName && run.project_name === project_name;
                            });

                            if (index >= 0) {
                                draftRuns.splice(index, 1);
                            }
                        });
                    }),
                );

                const patchGetAllRunResult = dispatch(
                    runApi.util.updateQueryData('getRuns', {}, (draftRuns) => {
                        runs_names.forEach((runName) => {
                            const index =
                                draftRuns?.findIndex((run) => {
                                    return run.run_spec.run_name === runName && run.project_name === project_name;
                                }) ?? -1;

                            if (index >= 0) {
                                draftRuns?.splice(index, 1);
                            }
                        });
                    }),
                );

                try {
                    await queryFulfilled;
                    // eslint-disable-next-line @typescript-eslint/no-unused-vars
                } catch (e) {
                    patchGetRunResult.undo();
                    patchGetAllRunResult.undo();
                }
            },
        }),

        getModels: builder.query<IModelExtended[], TModelsRequestParams>({
            // TODO: List models on the server. The runs list can't tell the runs that have a model,
            // so the browser reads runs page by page and keeps those with a model: every active run,
            // or the latest `MODELS_LATEST_RUNS_LIMIT` runs. The requests grow with the user's runs, not models,
            // and a stopped model of an older run is not found. A paged list of models on the server fixes both.
            queryFn: async (params, api, extraOptions, baseQuery) => {
                const runs: IRun[] = [];
                let lastRun: IRun | undefined;

                do {
                    const { data, error } = await baseQuery({
                        url: API.RUNS.LIST(),
                        method: 'POST',
                        body: {
                            ...params,
                            limit: RUNS_PAGE_LIMIT,
                            job_submissions_limit: 1,
                            prev_submitted_at: lastRun?.submitted_at,
                            prev_run_id: lastRun?.id,
                        },
                    });

                    if (error) {
                        return { error };
                    }

                    const page = data as IRun[];

                    runs.push(...page);
                    lastRun = page.length === RUNS_PAGE_LIMIT ? page[page.length - 1] : undefined;
                } while (lastRun && (params.only_active || runs.length < MODELS_LATEST_RUNS_LIMIT));

                return { data: runs.flatMap((run) => getExtendedModelFromRun(run) ?? []) };
            },

            // A page must not decide "Not Found" on an answer cached by an earlier visit
            keepUnusedDataFor: 0,

            providesTags: (result) =>
                result ? [...result.map(({ run }) => ({ type: 'Models' as const, id: run?.id })), 'Models'] : ['Models'],
        }),

        getMetrics: builder.query<IMetricsItem[], TJobMetricsRequestParams>({
            query: ({ project_name, run_name, ...params }) => {
                return {
                    url: API.PROJECTS.JOB_METRICS(project_name, run_name),
                    method: 'GET',
                    params,
                };
            },

            providesTags: ['Metrics'],
            transformResponse: ({ metrics }: { metrics: IMetricsItem[] }): IMetricsItem[] => {
                return metrics.map(({ timestamps, values, ...metric }) => ({
                    ...metric,
                    timestamps: timestamps.reverse(),
                    values: values.reverse(),
                }));
            },
        }),
    }),
});

export const {
    useGetRunsQuery,
    useLazyGetRunsQuery,
    useGetRunQuery,
    useApplyRunMutation,
    useStopRunsMutation,
    useDeleteRunsMutation,
    useGetModelsQuery,
    useGetMetricsQuery,
} = runApi;
