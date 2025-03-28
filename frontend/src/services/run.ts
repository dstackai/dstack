import { sortBy as _sortBy } from 'lodash';
import { API } from 'api';
import { BaseQueryMeta, BaseQueryResult } from '@reduxjs/toolkit/dist/query/baseQueryTypes';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

import { getExtendedModelFromRun } from '../libs/run';
import { unfinishedRuns } from '../pages/Runs/constants';

import { IModelExtended } from '../pages/Models/List/types';

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
                } catch (e) {
                    patchGetRunResult.undo();
                    patchGetAllRunResult.undo();
                }
            },
        }),

        getModels: builder.query<IModelExtended[], TRunsRequestParams>({
            query: (body = {}) => {
                return {
                    url: API.RUNS.LIST(),
                    method: 'POST',
                    body,
                };
            },

            transformResponse: (runs: IRun[]): IModelExtended[] => {
                return (
                    _sortBy<IRun>(runs, [(i) => -i.submitted_at])
                        // Should show models of active runs only
                        .filter((run) => unfinishedRuns.includes(run.status) && run.service?.model)
                        .reduce<IModelExtended[]>((acc, run) => {
                            const model = getExtendedModelFromRun(run);

                            if (model) acc.push(model);

                            return acc;
                        }, [])
                );
            },

            providesTags: (result) =>
                result ? [...result.map(({ id }) => ({ type: 'Models' as const, id: id })), 'Models'] : ['Models'],
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
    useStopRunsMutation,
    useDeleteRunsMutation,
    useLazyGetModelsQuery,
    useGetMetricsQuery,
} = runApi;
