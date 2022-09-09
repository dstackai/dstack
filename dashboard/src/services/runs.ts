import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';
import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const runApi = createApi({
    reducerPath: 'runApi',
    baseQuery: fetchBaseQuery({
        baseUrl: process.env.API_URL,
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Runs'],

    endpoints: (builder) => ({
        getRuns: builder.query<IRun[], IRunsFetchParams>({
            query: (params) => {
                return {
                    url: `/runs/query/?${new URLSearchParams({
                        n: params.count.toString(),
                        ...(params.repoUrl && { repo_url: params.repoUrl }),
                        ...(params.runName && { run_name: params.runName }),
                    }).toString()}`,
                };
            },

            transformResponse: (response: { runs: IRun[] }) => response.runs.sort((a, b) => b.submitted_at - a.submitted_at),

            providesTags: (result) =>
                result
                    ? [...result.map(({ run_name }) => ({ type: 'Runs', id: run_name } as const)), { type: 'Runs', id: 'LIST' }]
                    : [{ type: 'Runs', id: 'LIST' }],
        }),

        getRun: builder.query<IRun, IRun['run_name']>({
            query: (run_name) => {
                return {
                    url: `/runs/query/?${new URLSearchParams({ run_name }).toString()}`,
                };
            },

            transformResponse: (response: { runs: IRun[] }) => response.runs[0],
            providesTags: (result, error, runName) => [{ type: 'Runs', id: runName }],
        }),

        addTag: builder.mutation<void, Pick<IRun, 'run_name' | 'tag_name'>>({
            query: (body) => {
                return {
                    url: `/runs/tag`,
                    method: 'POST',
                    body,
                };
            },

            invalidatesTags: (result, error, { run_name }) => [{ type: 'Runs', id: run_name }],
        }),

        removeTag: builder.mutation<void, Pick<IRun, 'run_name'>>({
            query: (body) => {
                return {
                    url: `/runs/untag`,
                    method: 'POST',
                    body,
                };
            },

            invalidatesTags: (result, error, { run_name }) => [{ type: 'Runs', id: run_name }],
        }),

        resumeRun: builder.mutation<void, Pick<IRun, 'run_name'>>({
            query: (body) => {
                return {
                    url: `/runs/resume`,
                    method: 'POST',
                    body,
                };
            },

            invalidatesTags: (result, error, { run_name }) => [{ type: 'Runs', id: run_name }],
        }),

        stopRun: builder.mutation<void, Pick<IRun, 'run_name'> & { abort?: boolean }>({
            query: (body) => {
                return {
                    url: `/runs/stop`,
                    method: 'POST',
                    body,
                };
            },

            invalidatesTags: (result, error, { run_name }) => [{ type: 'Runs', id: run_name }],
        }),

        deleteRun: builder.mutation<void, Pick<IRun, 'run_name'>>({
            query: (body) => {
                return {
                    url: `/runs/delete`,
                    method: 'POST',
                    body,
                };
            },

            invalidatesTags: (result, error, { run_name }) => [
                { type: 'Runs', id: run_name },
                { type: 'Runs', id: 'LIST' },
            ],
        }),

        pruneRuns: builder.mutation<void, void>({
            query: () => {
                return {
                    url: `/runs/prune`,
                    method: 'POST',
                };
            },

            invalidatesTags: () => [{ type: 'Runs', id: 'LIST' }],
        }),

        refetchRuns: builder.mutation<null, void>({
            queryFn: () => ({ data: null }),
            invalidatesTags: [{ type: 'Runs', id: 'LIST' }],
        }),

        refetchRun: builder.mutation<null, IRun['run_name']>({
            queryFn: () => ({ data: null }),
            invalidatesTags: (result, error, runName) => [{ type: 'Runs', id: runName }],
        }),
    }),
});

export const {
    useGetRunsQuery,
    useGetRunQuery,
    useAddTagMutation,
    useRemoveTagMutation,
    useResumeRunMutation,
    useStopRunMutation,
    useDeleteRunMutation,
    usePruneRunsMutation,
    useRefetchRunsMutation,
    useRefetchRunMutation,
} = runApi;
