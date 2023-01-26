import { createApi } from '@reduxjs/toolkit/query/react';
import { fetchBaseQuery } from 'libs/fetchBaseQuery';
import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';
import { API } from 'api';

export const userApi = createApi({
    reducerPath: 'userApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    endpoints: (builder) => ({
        getUserData: builder.query<IUserSmall, { token: string }>({
            query: (params) => {
                return {
                    url: API.USERS.INFO() + `?token=${params.token}`,
                };
            },
        }),
    }),
});

export const { useGetUserDataQuery } = userApi;
