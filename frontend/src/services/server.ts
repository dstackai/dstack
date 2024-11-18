import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const serverApi = createApi({
    reducerPath: 'serverApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    endpoints: (builder) => ({
        getServerInfo: builder.query<
            {
                server_version: string;
            },
            void
        >({
            query: () => {
                return {
                    url: API.SERVER.INFO(),
                    method: 'POST',
                };
            },
        }),
    }),
});

export const { useGetServerInfoQuery } = serverApi;
