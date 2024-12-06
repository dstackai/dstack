import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

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

        getOktaInfo: builder.query<{ enabled: boolean }, void>({
            query: () => {
                return {
                    url: API.AUTH.OKTA.INFO(),
                    method: 'POST',
                };
            },
        }),

        oktaAuthorize: builder.mutation<{ authorization_url: string }, void>({
            query: () => ({
                url: API.AUTH.OKTA.AUTHORIZE(),
                method: 'POST',
            }),
        }),

        oktaCallback: builder.mutation<IUserWithCreds, { code: string; state: string }>({
            query: (body) => ({
                url: API.AUTH.OKTA.CALLBACK(),
                method: 'POST',
                body,
            }),
        }),
    }),
});

export const {
    useGithubAuthorizeMutation,
    useGithubCallbackMutation,
    useGetOktaInfoQuery,
    useOktaAuthorizeMutation,
    useOktaCallbackMutation,
} = authApi;
