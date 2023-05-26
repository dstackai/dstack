import { API } from 'api';
import { createApi } from '@reduxjs/toolkit/query/react';
import { fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const secretApi = createApi({
    reducerPath: 'secretApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Secrets'],

    endpoints: (builder) => ({
        getSecrets: builder.query<ISecret[], TGetSecretsRequestParams>({
            query: ({ project_name, ...body }) => {
                return {
                    url: API.PROJECTS.SECRET_LIST(project_name),
                    method: 'POST',
                    body,
                };
            },

            providesTags: (result) =>
                result
                    ? [...result.map(({ secret_name }) => ({ type: 'Secrets' as const, id: secret_name })), 'Secrets']
                    : ['Secrets'],
        }),

        createSecret: builder.mutation<ISecret['secret_name'], TAddSecretRequestParams>({
            query: ({ project_name, ...body }) => ({
                url: API.PROJECTS.SECRET_ADD(project_name),
                method: 'POST',
                body: body,
            }),

            invalidatesTags: ['Secrets'],
        }),
    }),
});

export const { useGetSecretsQuery, useCreateSecretMutation } = secretApi;
