import { API } from 'api';
import { createApi } from '@reduxjs/toolkit/query/react';
import { fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

const reduceInvalidateTagsFromRunNames = (names: IRun['run_name'][]) => {
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
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Runs', 'AllRuns'],

    endpoints: (builder) => ({
        getAllRuns: builder.query<IRunListItem[], void>({
            query: () => {
                return {
                    url: API.RUNS.LIST(),
                    method: 'POST',
                };
            },

            providesTags: (result) =>
                result
                    ? [...result.map(({ run_head }) => ({ type: 'AllRuns' as const, id: run_head.run_name })), 'AllRuns']
                    : ['AllRuns'],
        }),

        getRuns: builder.query<IRun[], TRunsRequestParams>({
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

        getRun: builder.query<IRun | undefined, TRunsRequestParams>({
            query: ({ name, ...body }) => {
                return {
                    url: API.PROJECTS.RUNS_LIST(name),
                    method: 'POST',
                    body,
                };
            },

            transformResponse: (response: IRun[]) => response[0],

            providesTags: (result) =>
                result
                    ? [
                          { type: 'Runs' as const, id: result?.run_name },
                          { type: 'AllRuns' as const, id: result?.run_name },
                      ]
                    : [],
        }),

        stopRuns: builder.mutation<void, TStopRunsRequestParams>({
            query: ({ name, ...body }) => ({
                url: API.PROJECTS.RUNS_STOP(name),
                method: 'POST',
                body,
            }),

            invalidatesTags: (result, error, params) => reduceInvalidateTagsFromRunNames(params.run_names),
        }),

        deleteRuns: builder.mutation<void, TDeleteRunsRequestParams>({
            query: ({ name, ...body }) => ({
                url: API.PROJECTS.RUNS_DELETE(name),
                method: 'POST',
                body,
            }),

            invalidatesTags: (result, error, params) => reduceInvalidateTagsFromRunNames(params.run_names),
        }),
    }),
});

export const { useGetAllRunsQuery, useGetRunsQuery, useGetRunQuery, useStopRunsMutation, useDeleteRunsMutation } = runApi;
