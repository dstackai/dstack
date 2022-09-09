import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';
import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const userApi = createApi({
    reducerPath: 'userApi',
    baseQuery: fetchBaseQuery({
        baseUrl: process.env.API_URL,
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Users'],

    endpoints: (builder) => ({
        getUserInfo: builder.query<IUser, void>({
            query: () => {
                return {
                    url: '/users/info',
                    method: 'GET',
                };
            },

            providesTags: [{ type: 'Users', id: 'CURRENT_USER' }],
        }),

        login: builder.mutation<ILoginRequestResponse, ILoginRequestParams>({
            query: (body) => {
                return {
                    url: `/users/login`,
                    method: 'POST',
                    body,
                };
            },

            invalidatesTags: [{ type: 'Users', id: 'CURRENT_USER' }],
        }),

        signUp: builder.mutation<ISignUpRequestResponse, ISignUpRequestParams>({
            query: (body) => {
                return {
                    url: `/users/register`,
                    method: 'POST',
                    body,
                };
            },

            invalidatesTags: [{ type: 'Users', id: 'CURRENT_USER' }],
        }),

        updateAwsConfig: builder.mutation<void, Partial<IAWSConfig>>({
            query: (body) => {
                return {
                    url: `/users/aws/config`,
                    method: 'POST',
                    body,
                };
            },

            invalidatesTags: [{ type: 'Users', id: 'CURRENT_USER' }],
        }),

        clearAwsConfig: builder.mutation<void, void>({
            query: () => {
                return {
                    url: `/users/aws/clear`,
                    method: 'POST',
                };
            },

            invalidatesTags: [{ type: 'Users', id: 'CURRENT_USER' }],
        }),

        testAwsConfig: builder.mutation<void, Partial<IAWSConfig>>({
            query: (body) => {
                return {
                    url: `/users/aws/test`,
                    method: 'POST',
                    body,
                };
            },
        }),

        unlinkGithubAccount: builder.mutation<void, void>({
            query: () => {
                return {
                    url: `/users/github/unlink`,
                    method: 'POST',
                };
            },

            invalidatesTags: [{ type: 'Users', id: 'CURRENT_USER' }],
        }),
    }),
});

export const {
    useGetUserInfoQuery,
    useUpdateAwsConfigMutation,
    useClearAwsConfigMutation,
    useLoginMutation,
    useSignUpMutation,
    useTestAwsConfigMutation,
    useUnlinkGithubAccountMutation,
} = userApi;
