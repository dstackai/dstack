import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const meteringApi = createApi({
    reducerPath: 'meteringApi',
    refetchOnMountOrArgChange: true,
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    endpoints: (builder) => ({
        getMetering: builder.query<IMeteringRow[], TMeteringListRequestParams>({
            query: (body) => {
                return {
                    url: API.METERING.LIST(),
                    method: 'POST',
                    body,
                };
            },

            transformResponse: (response: { rows: IMeteringRow[] }) => response.rows,
        }),
    }),
});

export const { useGetMeteringQuery, useLazyGetMeteringQuery } = meteringApi;
