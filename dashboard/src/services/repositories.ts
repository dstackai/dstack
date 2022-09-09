import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';
import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

interface IRepositoriesFetchParams {
    user_name?: string;
}

export const repositoryApi = createApi({
    reducerPath: 'repositoryApi',
    baseQuery: fetchBaseQuery({
        baseUrl: process.env.API_URL,
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Repositories'],

    endpoints: (builder) => ({
        getRepositories: builder.query<IRepository[], IRepositoriesFetchParams>({
            query: (params) => {
                return {
                    url: `/repos/query?${new URLSearchParams({
                        ...(params.user_name && { user_name: params.user_name }),
                    }).toString()}`,
                };
            },

            transformResponse: (response: { repos: IRepository[] }) => response.repos,

            providesTags: (result) =>
                result
                    ? [
                          ...result.map(({ repo_name }) => ({ type: 'Repositories', id: repo_name } as const)),
                          { type: 'Repositories', id: 'LIST' },
                      ]
                    : [{ type: 'Repositories', id: 'LIST' }],
        }),

        refetchRepositories: builder.mutation<null, void>({
            queryFn: () => ({ data: null }),
            invalidatesTags: [{ type: 'Repositories', id: 'LIST' }],
        }),
    }),
});

export const { useGetRepositoriesQuery, useRefetchRepositoriesMutation } = repositoryApi;
