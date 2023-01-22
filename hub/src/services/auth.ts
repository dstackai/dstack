import { createApi } from '@reduxjs/toolkit/query/react';
import { fetchBaseQuery } from 'libs/fetchBaseQuery';
import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const authApi = createApi({
    reducerPath: 'authApi',
    baseQuery: fetchBaseQuery({
        baseUrl: process.env.API_URL,
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    endpoints: (builder) => ({
        checkToken: builder.mutation<IUserSmall, { token: string }>({
            query: (body) => {
                return {
                    url: `/auth/token`,
                    method: 'POST',
                    body,
                };
            },
        }),
    }),
});

export const { useCheckTokenMutation } = authApi;
