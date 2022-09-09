import { createApi } from '@reduxjs/toolkit/query/react';
import { fetchBaseQuery } from '@reduxjs/toolkit/dist/query/react';
import fetchBaseQueryHeaders from '../libs/fetchBaseQueryHeaders';

export const secretApi = createApi({
    reducerPath: 'secretApi',
    baseQuery: fetchBaseQuery({
        baseUrl: process.env.API_URL,
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Secrets'],

    endpoints: (builder) => ({
        getSecrets: builder.query<ISecret[], void>({
            query: () => {
                return {
                    url: '/secrets/query',
                    method: 'GET',
                };
            },

            transformResponse: (response: { secrets: ISecret[] }) => response.secrets,

            providesTags: [{ type: 'Secrets' }],
        }),

        addSecret: builder.mutation<void, Omit<ISecret, 'secret_id'>>({
            query: (body) => {
                return {
                    url: `/secrets/add`,
                    method: 'POST',
                    body,
                };
            },

            invalidatesTags: [{ type: 'Secrets' }],
        }),

        updateSecret: builder.mutation<void, ISecret>({
            query: (body) => {
                return {
                    url: `/secrets/update`,
                    method: 'POST',
                    body,
                };
            },

            invalidatesTags: [{ type: 'Secrets' }],
        }),

        deleteSecret: builder.mutation<void, Pick<ISecret, 'secret_id'>>({
            query: (body) => {
                return {
                    url: `/secrets/delete`,
                    method: 'POST',
                    body,
                };
            },

            invalidatesTags: [{ type: 'Secrets' }],
        }),
    }),
});

export const { useGetSecretsQuery, useAddSecretMutation, useUpdateSecretMutation, useDeleteSecretMutation } = secretApi;
