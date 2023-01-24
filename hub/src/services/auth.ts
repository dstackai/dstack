import { createApi } from '@reduxjs/toolkit/query/react';
import { fetchBaseQuery } from 'libs/fetchBaseQuery';
import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';
import { API } from 'api';

export const authApi = createApi({
    reducerPath: 'authApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    endpoints: (builder) => ({
        checkToken: builder.mutation<IUserSmall, { token: string }>({
            query: (body) => {
                return {
                    url: API.AUTH.TOKEN(),
                    method: 'POST',
                    body,
                };
            },
        }),
    }),
});

export const { useCheckTokenMutation } = authApi;
