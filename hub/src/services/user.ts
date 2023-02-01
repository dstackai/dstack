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
        getUserData: builder.query<IUserSmall, void>({
            query: () => {
                return {
                    url: API.USERS.INFO(),
                };
            },
        }),

        getUserList: builder.query<IUser[], void>({
            query: () => {
                return {
                    url: API.USERS.LIST(),
                };
            },
        }),
    }),
});

export const { useGetUserDataQuery, useGetUserListQuery } = userApi;
