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
                body: hub,
            }),

            invalidatesTags: (result) => [{ type: 'Hubs' as const, id: result?.hub_name }],
        }),

        updateHub: builder.mutation<IHub, Partial<IHub> & Pick<IHub, 'hub_name'>>({
            query: (hub) => ({
                url: API.HUBS.DETAILS(hub.hub_name),
                method: 'PATCH',
                body: hub,
            }),

            invalidatesTags: (result) => [{ type: 'Hubs' as const, id: result?.hub_name }],
        }),

        updateHubMembers: builder.mutation<IHub, Pick<IHub, 'hub_name' | 'members'>>({
            query: (hub) => ({
                url: API.HUBS.MEMBERS(hub.hub_name),
                method: 'POST',
                body: hub.members,
            }),

            invalidatesTags: (result, error, params) => [{ type: 'Hubs' as const, id: params?.hub_name }],
        }),

        deleteHubs: builder.mutation<void, IHub['hub_name'][]>({
            query: (hubNames) => ({
                url: API.HUBS.BASE(),
                method: 'DELETE',
                body: {
                    hubs: hubNames,
                },
            }),
        }),

        backendValues: builder.mutation<IHubAwsBackendValues, Partial<THubBackend>>({
            query: (data) => ({
                url: API.HUBS.BACKEND_VALUES(),
                method: 'POST',
                body: data,
            }),
        }),
    }),
});

export const {
    useGetHubsQuery,
    useGetHubQuery,
    useCreateHubMutation,
    useUpdateHubMutation,
    useUpdateHubMembersMutation,
    useDeleteHubsMutation,
    useBackendValuesMutation,
} = hubApi;
