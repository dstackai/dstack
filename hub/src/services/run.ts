import { API } from 'api';
import { createApi } from '@reduxjs/toolkit/query/react';
import { fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

import { DeleteRunsRequestParams, RunsRequestParams, StopRunsRequestParams } from './run.types';

export const runApi = createApi({
    reducerPath: 'runApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Runs'],

    endpoints: (builder) => ({
        getRuns: builder.query<IRun[], RunsRequestParams>({
            query: ({ name, ...body }) => {
                return {
                    url: API.PROJECTS.RUNS_LIST(name),
                    method: 'POST',
                    body,
                };
            },

            providesTags: (result) =>
                result ? [...result.map(({ run_name }) => ({ type: 'Runs' as const, id: run_name })), 'Runs'] : ['Runs'],
        }),

        getRun: builder.query<IRun | undefined, RunsRequestParams>({
            query: ({ name, ...body }) => {
                return {
                    url: API.PROJECTS.RUNS_LIST(name),
                    method: 'POST',
                    body,
                };
            },

            transformResponse: (response: IRun[]) => response[0],

            providesTags: (result) => (result ? [{ type: 'Runs' as const, id: result?.run_name }] : []),
        }),

        stopRuns: builder.mutation<void, StopRunsRequestParams>({
            query: ({ name, ...body }) => ({
                url: API.PROJECTS.RUNS_STOP(name),
                method: 'POST',
                body,
            }),

            invalidatesTags: (result, error, params) => params.run_names.map((run) => ({ type: 'Runs' as const, id: run })),
        }),

        deleteRuns: builder.mutation<void, DeleteRunsRequestParams>({
            query: ({ name, ...body }) => ({
                url: API.PROJECTS.RUNS_DELETE(name),
                method: 'POST',
                body,
            }),

            invalidatesTags: (result, error, params) => params.run_names.map((run) => ({ type: 'Runs' as const, id: run })),
        }),
    }),
});

export const { useGetRunsQuery, useGetRunQuery, useStopRunsMutation, useDeleteRunsMutation } = runApi;
