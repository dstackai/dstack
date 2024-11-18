import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const poolApi = createApi({
    reducerPath: 'poolApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Pools', 'Pool'],

    endpoints: (builder) => ({
        getPools: builder.query<IPoolListItem[], { projectName: IProject['project_name'] }>({
            query: ({ projectName }) => {
                return {
                    url: API.PROJECTS.POOLS(projectName),
                    method: 'POST',
                };
            },

            providesTags: (result) =>
                result ? [...result.map(({ name }) => ({ type: 'Pools' as const, id: name })), 'Pools'] : ['Pools'],
        }),

        getPoolsInstances: builder.query<IInstanceListItem[], TPoolInstancesRequestParams | undefined>({
            query: (body) => {
                return {
                    url: API.POOLS.INSTANCES_LIST(),
                    method: 'POST',
                    body,
                };
            },

            providesTags: (result) =>
                result ? [...result.map(({ name }) => ({ type: 'Pools' as const, id: name })), 'Pools'] : ['Pools'],
        }),

        getPoolDetails: builder.query<IPool, { projectName: IProject['project_name']; poolName: IPool['name'] }>({
            query: ({ projectName, poolName }) => {
                return {
                    url: API.PROJECTS.POOL_DETAILS(projectName),
                    method: 'POST',
                    body: { name: poolName },
                };
            },

            providesTags: (result) => (result ? [{ type: 'Pools' as const, id: result.name }] : []),
        }),
    }),
});

export const { useGetPoolsQuery, useGetPoolsInstancesQuery, useLazyGetPoolsInstancesQuery, useGetPoolDetailsQuery } = poolApi;
