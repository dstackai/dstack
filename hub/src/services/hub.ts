import { createApi } from '@reduxjs/toolkit/query/react';
import { fetchBaseQuery } from 'libs/fetchBaseQuery';
import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';
import { API } from 'api';

export const hubApi = createApi({
    reducerPath: 'hubApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Hubs'],

    endpoints: (builder) => ({
        getHubs: builder.query<IHub[], void>({
            query: () => {
                return {
                    url: API.HUBS.LIST(),
                };
            },

            providesTags: (result) =>
                result ? [...result.map(({ hub_name }) => ({ type: 'Hubs' as const, id: hub_name })), 'Hubs'] : ['Hubs'],
        }),

        getHub: builder.query<IHub, { name: IHub['hub_name'] }>({
            query: ({ name }) => {
                return {
                    url: API.HUBS.DETAILS(name),
                };
            },

            providesTags: (result) => (result ? [{ type: 'Hubs' as const, id: result.hub_name }] : []),
        }),

        createHub: builder.mutation<IHub, IHub>({
            query: (hub) => ({
                url: API.HUBS.BASE(),
                method: 'POST',
                params: hub,
            }),

            invalidatesTags: (result) => [{ type: 'Hubs' as const, id: result?.hub_name }],
        }),

        updateHub: builder.mutation<IHub, Partial<IHub> & Pick<IHub, 'hub_name'>>({
            query: (hub) => ({
                url: API.USERS.DETAILS(hub.hub_name),
                method: 'PATCH',
                params: hub,
            }),

            invalidatesTags: (result) => [{ type: 'Hubs' as const, id: result?.hub_name }],
        }),

        deleteHubs: builder.mutation<void, IHub['hub_name'][]>({
            query: (hubNames) => ({
                url: API.HUBS.BASE(),
                method: 'DELETE',
                params: {
                    hubs: hubNames,
                },
            }),
        }),
    }),
});

export const { useGetHubsQuery, useGetHubQuery, useCreateHubMutation, useUpdateHubMutation, useDeleteHubsMutation } = hubApi;
