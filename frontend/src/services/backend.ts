import { API } from 'api';

import { projectApi } from './project';

export const extendedProjectApi = projectApi.injectEndpoints({
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

            invalidatesTags: (result, error, arg) => [{ type: 'Projects' as const, id: arg.projectName }],
        }),

        updateBackend: builder.mutation<TBackendConfig, { projectName: IProject['project_name']; config: TBackendConfig }>({
            query: ({ projectName, config }) => ({
                url: API.PROJECT_BACKENDS.UPDATE(projectName),
                method: 'POST',
                body: config,
            }),

            invalidatesTags: (result, error, arg) => [
                { type: 'Projects' as const, id: arg.projectName },
                { type: 'Backends' as const, id: result?.type },
            ],
        }),

        backendValues: builder.mutation<TBackendValuesResponse, Partial<TBackendConfig>>({
            query: (data) => ({
                url: API.BACKENDS.CONFIG_VALUES(),
                method: 'POST',
                body: data,
            }),
        }),

        getBackendConfig: builder.query<
            TBackendConfig,
            { projectName: IProject['project_name']; backendName: IProjectBackend['name'] }
        >({
            query: ({ projectName, backendName }) => {
                return {
                    url: API.PROJECT_BACKENDS.BACKEND_CONFIG_INFO(projectName, backendName),
                    method: 'POST',
                };
            },

            providesTags: (result, error, arg) => (result ? [{ type: 'Backends' as const, id: arg.backendName }] : []),
        }),

        createBackendViaYaml: builder.mutation<void, { projectName: IProject['project_name']; backend: IBackendConfigYaml }>({
            query: ({ projectName, backend }) => ({
                url: API.PROJECT_BACKENDS.CREATE_YAML(projectName),
                method: 'POST',
                body: backend,
            }),
        }),

        updateBackendViaYaml: builder.mutation<void, { projectName: IProject['project_name']; backend: IBackendConfigYaml }>({
            query: ({ projectName, backend }) => ({
                url: API.PROJECT_BACKENDS.UPDATE_YAML(projectName),
                method: 'POST',
                body: backend,
            }),
        }),

        getBackendYaml: builder.query<IBackendConfigYaml, { projectName: IProject['project_name']; backendName: string }>({
            query: ({ projectName, backendName }) => ({
                url: API.PROJECT_BACKENDS.GET_YAML(projectName, backendName),
                method: 'POST',
            }),
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
            { projectName: IProject['project_name']; backends_names: IProjectBackend['name'][] }
        >({
            query: ({ projectName, backends_names }) => ({
                url: API.PROJECT_BACKENDS.DELETE(projectName),
                method: 'POST',
                body: { backends_names },
            }),

            invalidatesTags: (result, error, arg) => [{ type: 'Projects' as const, id: arg.projectName }, { type: 'Backends' }],
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
    useCreateBackendViaYamlMutation,
    useUpdateBackendViaYamlMutation,
    useGetBackendYamlQuery,
} = extendedProjectApi;
