import { createApi } from '@reduxjs/toolkit/query/react';
import { fetchBaseQuery } from 'libs/fetchBaseQuery';
import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';
import { API } from 'api';

export const hubApi = createApi({
    reducerPath: 'hubApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    endpoints: (builder) => ({
        getHubs: builder.query<IHub[], void>({
            query: () => {
                return {
                    url: API.HUBS.LIST(),
                };
            },
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

export const { useGetHubsQuery, useDeleteHubsMutation } = hubApi;
