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

        getEntraInfo: builder.query<{ enabled: boolean }, void>({
            query: () => {
                return {
                    url: API.AUTH.ENTRA.INFO(),
                    method: 'POST',
                };
            },
        }),

        entraAuthorize: builder.mutation<{ authorization_url: string }, { base_url: string }>({
            query: (body) => ({
                url: API.AUTH.ENTRA.AUTHORIZE(),
                method: 'POST',
                body,
            }),
        }),

        entraCallback: builder.mutation<IUserWithCreds, { code: string; state: string; base_url: string }>({
            query: (body) => ({
                url: API.AUTH.ENTRA.CALLBACK(),
                method: 'POST',
                body,
            }),
        }),

        getGoogleInfo: builder.query<{ enabled: boolean }, void>({
            query: () => {
                return {
                    url: API.AUTH.GOOGLE.INFO(),
                    method: 'POST',
                };
            },
        }),

        googleAuthorize: builder.mutation<{ authorization_url: string }, void>({
            query: () => ({
                url: API.AUTH.GOOGLE.AUTHORIZE(),
                method: 'POST',
            }),
        }),

        googleCallback: builder.mutation<IUserWithCreds, { code: string; state: string }>({
            query: (body) => ({
                url: API.AUTH.GOOGLE.CALLBACK(),
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
    useGetEntraInfoQuery,
    useEntraAuthorizeMutation,
    useEntraCallbackMutation,
    useGetGoogleInfoQuery,
    useGoogleAuthorizeMutation,
    useGoogleCallbackMutation,
} = authApi;
