import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

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

    tagTypes: ['Runs'],

    endpoints: (builder) => ({
        getRuns: builder.query<IRun[], TRunsRequestParams | void>({
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

        getRun: builder.query<IRun | undefined, { project_name: string; run_name: string }>({
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
                    runApi.util.updateQueryData('getRuns', undefined, (draftRuns) => {
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
    }),
});

export const { useGetRunsQuery, useLazyGetRunsQuery, useGetRunQuery, useStopRunsMutation, useDeleteRunsMutation } = runApi;
