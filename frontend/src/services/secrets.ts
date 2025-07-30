import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const secretApi = createApi({
    reducerPath: 'secretApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Secrets'],

    endpoints: (builder) => ({
        getAllSecrets: builder.query<IProjectSecret[], { project_name: string }>({
            query: ({ project_name }) => {
                return {
                    url: API.PROJECTS.SECRETS_LIST(project_name),
                    method: 'POST',
                };
            },

            providesTags: (result) =>
                result ? [...result.map(({ id }) => ({ type: 'Secrets' as const, id: id })), 'Secrets'] : ['Secrets'],
        }),

        getSecret: builder.query<IProjectSecret, { project_name: IProject['project_name']; name: IProjectSecret['name'] }>({
            query: ({ project_name, name }) => ({
                url: API.PROJECTS.SECRET_GET(project_name),
                method: 'POST',
                body: {
                    name,
                },
            }),

            providesTags: (result) => (result ? [{ type: 'Secrets' as const, id: result.id }, 'Secrets'] : ['Secrets']),
        }),

        updateSecret: builder.mutation<
            void,
            { project_name: IProject['project_name']; name: IProjectSecret['name']; value: IProjectSecret['value'] }
        >({
            query: ({ project_name, ...body }) => ({
                url: API.PROJECTS.SECRETS_UPDATE(project_name),
                method: 'POST',
                body: body,
            }),

            invalidatesTags: () => ['Secrets'],
        }),

        deleteSecrets: builder.mutation<void, { project_name: IProject['project_name']; names: IProjectSecret['name'][] }>({
            query: ({ project_name, names }) => ({
                url: API.PROJECTS.SECRETS_DELETE(project_name),
                method: 'POST',
                body: {
                    secrets_names: names,
                },
            }),

            invalidatesTags: () => ['Secrets'],
        }),
    }),
});

export const {
    useGetAllSecretsQuery,
    useGetSecretQuery,
    useLazyGetSecretQuery,
    useUpdateSecretMutation,
    useDeleteSecretsMutation,
} = secretApi;
