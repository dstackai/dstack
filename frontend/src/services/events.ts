import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const eventApi = createApi({
    reducerPath: 'eventApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Events'],

    endpoints: (builder) => ({
        getAllEvents: builder.query<IEvent[], TEventListRequestParams>({
            query: (body) => {
                return {
                    url: API.EVENTS.LIST(),
                    method: 'POST',
                    body,
                };
            },

            providesTags: (result) =>
                result ? [...result.map(({ id }) => ({ type: 'Events' as const, id: id })), 'Events'] : ['Events'],
        }),
    }),
});

export const { useGetAllEventsQuery, useLazyGetAllEventsQuery } = eventApi;
