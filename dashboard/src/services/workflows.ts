import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';
import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

type GenericRequestParams = Partial<Pick<IRunWorkflow, 'run_name' | 'workflow_name'>>;

type DeleteRequestParams = {
    repo_user_name: string;
    repo_name: string;
    run_name?: string;
    all_run?: boolean;
    failed_runs?: boolean;
};

const getWorkflowId = ({ run_name, workflow_name }: GenericRequestParams): string => {
    return `${run_name}/${workflow_name}`;
};

export const workflowApi = createApi({
    reducerPath: 'workflowApi',
    baseQuery: fetchBaseQuery({
        baseUrl: process.env.API_URL,
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Workflows'],

    endpoints: (builder) => ({
        getWorkflows: builder.query<IRunWorkflow[], IRunWorkflowsFetchParams>({
            query: (params) => {
                return {
                    url: `/runs/query?${new URLSearchParams({
                        n: params.count.toString(),
                        ...(params.userName && { user_name: params.userName }),
                        ...(params.repoUserName && { repo_user_name: params.repoUserName }),
                        ...(params.repoName && { repo_name: params.repoName }),
                        ...(params.tagName && { tag_name: params.tagName }),
                    }).toString()}`,
                };
            },

            transformResponse: (response: { runs: IRunWorkflow[] }) => response.runs,

            providesTags: (result) =>
                result
                    ? [
                          ...result.map(
                              ({ workflow_name, run_name }) =>
                                  ({ type: 'Workflows', id: getWorkflowId({ run_name, workflow_name }) } as const),
                          ),
                          { type: 'Workflows', id: 'LIST' },
                      ]
                    : [{ type: 'Workflows', id: 'LIST' }],
        }),

        getWorkflow: builder.query<IRunWorkflow, IRunWorkflowFetchParams>({
            query: (params) => {
                return {
                    url: `/runs/get?${new URLSearchParams({
                        ...(params.repoUserName && { repo_user_name: params.repoUserName }),
                        ...(params.repoName && { repo_name: params.repoName }),
                        ...(params.runName && { run_name: params.runName }),
                    }).toString()}`,
                };
            },

            transformResponse: (response: { run: IRunWorkflow }) => response.run,
            providesTags: (result, error, { runName }) => [{ type: 'Workflows', id: runName }],
        }),

        addTag: builder.mutation<void, Pick<IRunWorkflow, 'run_name' | 'workflow_name' | 'tag_name'>>({
            query: (body) => {
                return {
                    url: `/runs/tag`,
                    method: 'POST',
                    body,
                };
            },

            invalidatesTags: (result, error, { run_name, workflow_name }) => [
                { type: 'Workflows', id: getWorkflowId({ run_name, workflow_name }) },
            ],
        }),

        removeTag: builder.mutation<void, GenericRequestParams>({
            query: (body) => {
                return {
                    url: `/runs/untag`,
                    method: 'POST',
                    body,
                };
            },

            invalidatesTags: (result, error, { run_name, workflow_name }) => [
                { type: 'Workflows', id: getWorkflowId({ run_name, workflow_name }) },
            ],
        }),

        restart: builder.mutation<void, GenericRequestParams & { clear?: boolean }>({
            query: (body) => {
                return {
                    url: `/runs/restart`,
                    method: 'POST',
                    body,
                };
            },

            invalidatesTags: (result, error, { run_name, workflow_name }) => [
                { type: 'Workflows', id: getWorkflowId({ run_name, workflow_name }) },
            ],
        }),

        stop: builder.mutation<void, GenericRequestParams & { abort?: boolean }>({
            query: (body) => {
                return {
                    url: '/runs/stop',
                    method: 'POST',
                    body,
                };
            },

            invalidatesTags: (result, error, { run_name, workflow_name }) => [
                { type: 'Workflows', id: getWorkflowId({ run_name, workflow_name }) },
            ],
        }),

        delete: builder.mutation<void, DeleteRequestParams>({
            query: (body) => {
                return {
                    url: `/runs/delete`,
                    method: 'POST',
                    body,
                };
            },

            invalidatesTags: () => [{ type: 'Workflows', id: 'LIST' }],
        }),

        refetchWorkflows: builder.mutation<null, void>({
            queryFn: () => ({ data: null }),
            invalidatesTags: [{ type: 'Workflows', id: 'LIST' }],
        }),

        refetchWorkflow: builder.mutation<null, Pick<IRunWorkflow, 'run_name' | 'workflow_name'>>({
            queryFn: () => ({ data: null }),
            invalidatesTags: (result, error, { run_name, workflow_name }) => [
                { type: 'Workflows', id: getWorkflowId({ run_name, workflow_name }) },
            ],
        }),
    }),
});

export const {
    useGetWorkflowsQuery,
    useGetWorkflowQuery,
    useAddTagMutation,
    useRemoveTagMutation,
    useRestartMutation,
    useStopMutation,
    useDeleteMutation,
    useRefetchWorkflowsMutation,
    useRefetchWorkflowMutation,
} = workflowApi;
