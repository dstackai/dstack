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

            invalidatesTags: () => ['Backends'],
        }),

        updateBackend: builder.mutation<TBackendConfig, { projectName: IProject['project_name']; config: TBackendConfig }>({
            query: ({ projectName, config }) => ({
                url: API.PROJECT_BACKENDS.UPDATE(projectName),
                method: 'POST',
                body: config,
            }),

            invalidatesTags: (result) => [{ type: 'Backends' as const, id: result?.type }],
        }),

        backendValues: builder.mutation<TBackendValuesResponse, Partial<TBackendConfig>>({
            query: (data) => ({
                url: API.BACKENDS.CONFIG_VALUES(),
                method: 'POST',
                body: data,
            }),
        }),

        getBackendConfig: builder.query<
            IProjectBackend,
            { projectName: IProject['project_name']; backendName: IProjectBackend['name'] }
        >({
            query: ({ projectName, backendName }) => {
                return {
                    url: API.PROJECT_BACKENDS.BACKEND_CONFIG_INFO(projectName, backendName),
                    method: 'POST',
                };
            },

            providesTags: (result) => (result ? [{ type: 'Backends' as const, id: result.name }] : []),
        }),

        getProjectBackends: builder.query<IProjectBackend[], { projectName: IProject['project_name'] }>({
            query: ({ projectName }) => {
                return {
                    url: API.PROJECT_BACKENDS.LIST(projectName),
                    method: 'POST',
                };
            },

            providesTags: (result) =>
                result ? [...result.map(({ name }) => ({ type: 'Backends' as const, id: name })), 'Backends'] : ['Backends'],
        }),

        deleteProjectBackend: builder.mutation<
            void,
            { projectName: IProject['project_name']; backends: IProjectBackend['name'][] }
        >({
            query: ({ projectName, backends }) => ({
                url: API.PROJECT_BACKENDS.DELETE(projectName),
                method: 'POST',
                body: { backends },
            }),

            invalidatesTags: () => ['Backends'],
        }),
    }),
});

export const {
    useGetBackendTypesQuery,
    useDeleteProjectBackendMutation,
    useCreateBackendMutation,
    useBackendValuesMutation,
    useGetBackendConfigQuery,
    useUpdateBackendMutation,
    useGetProjectBackendsQuery,
} = backendApi;
