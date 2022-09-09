import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';
import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const runnerApi = createApi({
    reducerPath: 'runnerApi',
    baseQuery: fetchBaseQuery({
        baseUrl: process.env.API_URL,
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Runners'],

    endpoints: (builder) => ({
        getRunners: builder.query<IRunner[], void>({
            query: () => {
                return {
                    url: '/runners/query',
                };
            },

            transformResponse: (response: { runners: IRunner[] }) => response.runners,

            providesTags: (result) =>
                result
                    ? [
                          ...result.map(({ runner_id }) => ({ type: 'Runners', id: runner_id } as const)),
                          { type: 'Runners', id: 'LIST' },
                      ]
                    : [{ type: 'Runners', id: 'LIST' }],
        }),

        refetchRunners: builder.mutation<null, void>({
            queryFn: () => ({ data: null }),
            invalidatesTags: [{ type: 'Runners', id: 'LIST' }],
        }),
    }),
});

export const { useGetRunnersQuery, useRefetchRunnersMutation } = runnerApi;
