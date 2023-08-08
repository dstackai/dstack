import { API } from 'api';
import { createApi } from '@reduxjs/toolkit/query/react';
import { fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const backendApi = createApi({
    reducerPath: 'backendApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Backends'],

    endpoints: (builder) => ({
        getBackendTypes: builder.query<TBackendType[], void>({
            query: () => ({
                url: API.BACKENDS.LIST_TYPES(),
                method: 'POST',
            }),
        }),

        createBackend: builder.mutation<TBackendConfig, { projectName: IProject['project_name']; config: TBackendConfig }>({
            query: ({ projectName, config }) => ({
                url: API.PROJECT_BACKENDS.CREATE(projectName),
                method: 'POST',
                body: config,
            }),
        }),

        backendValues: builder.mutation<TBackendValuesResponse, Partial<TBackendConfig>>({
            query: (data) => ({
                url: API.BACKENDS.CONFIG_VALUES(),
                method: 'POST',
                body: data,
            }),
        }),

        getBackendConfig: builder.query<IBackend, { projectName: IProject['project_name']; backendName: IBackend['name'] }>({
            query: ({ projectName, backendName }) => {
                return {
                    url: API.PROJECT_BACKENDS.BACKEND_CONFIG_INFO(projectName, backendName),
                    method: 'POST',
                };
            },

            providesTags: (result) => (result ? [{ type: 'Backends' as const, id: result.name }] : []),
        }),

        getProjectBackends: builder.query<IBackend, { projectName: IProject['project_name'] }>({
            query: ({ projectName }) => {
                return {
                    url: API.PROJECT_BACKENDS.LIST(projectName),
                    method: 'POST',
                };
            },

            providesTags: (result) => (result ? [{ type: 'Backends' as const, id: result.name }] : []),
        }),
    }),
});

export const {
    useGetBackendTypesQuery,
    useCreateBackendMutation,
    useBackendValuesMutation,
    useGetBackendConfigQuery,
    useGetProjectBackendsQuery,
} = backendApi;
