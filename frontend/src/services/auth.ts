import { API } from 'api';
import { createApi } from '@reduxjs/toolkit/query/react';
import { fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import unauthorizedQueryHeaders from 'libs/fetchBaseQueryHeaders';


export const authApi = createApi({
    reducerPath: 'authApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: unauthorizedQueryHeaders,
    }),

    tagTypes: ['Auth'],

    endpoints: (builder) => ({
        githubAuthorize: builder.mutation<{ authorization_url: string }, void>({
            query: () => ({
                url: API.AUTH.GITHUB.AUTHORIZE(),
                method: 'POST',
            }),
        }),

        githubCallback: builder.mutation<IUserWithCreds, { code: string }>({
            query: (body) => ({
                url: API.AUTH.GITHUB.CALLBACK(),
                method: 'POST',
                body,
            }),
        }),
    }),
});

export const { useGithubAuthorizeMutation, useGithubCallbackMutation } = authApi;
