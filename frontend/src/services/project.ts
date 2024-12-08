import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import { base64ToArrayBuffer } from 'libs';
import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const projectApi = createApi({
    reducerPath: 'projectApi',
    refetchOnMountOrArgChange: true,
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Projects', 'ProjectRepos', 'ProjectLogs', 'Backends'],

    endpoints: (builder) => ({
        getProjects: builder.query<IProject[], void>({
            query: () => {
                return {
                    url: API.PROJECTS.LIST(),
                    method: 'POST',
                };
            },

            providesTags: (result) =>
                result
                    ? [...result.map(({ project_name }) => ({ type: 'Projects' as const, id: project_name })), 'Projects']
                    : ['Projects'],
        }),

        getProject: builder.query<IProject, { name: IProject['project_name'] }>({
            query: ({ name }) => {
                return {
                    url: API.PROJECTS.DETAILS_INFO(name),
                    method: 'POST',
                };
            },

            providesTags: (result) => (result ? [{ type: 'Projects' as const, id: result.project_name }] : []),
        }),

        createProject: builder.mutation<IProject, IProject>({
            query: (project) => ({
                url: API.PROJECTS.CREATE(),
                method: 'POST',
                body: project,
            }),

            invalidatesTags: () => ['Projects'],
        }),

        updateProjectMembers: builder.mutation<IProject, TSetProjectMembersParams>({
            query: ({ project_name, members }) => ({
                url: API.PROJECTS.SET_MEMBERS(project_name),
                method: 'POST',
                body: {
                    members,
                },
            }),

            invalidatesTags: (result, error, params) => [{ type: 'Projects' as const, id: params?.project_name }],
        }),

        deleteProjects: builder.mutation<void, IProject['project_name'][]>({
            query: (projectNames) => ({
                url: API.PROJECTS.DELETE(),
                method: 'POST',
                body: {
                    projects_names: projectNames,
                },
            }),

            invalidatesTags: () => ['Projects'],
        }),

        getProjectLogs: builder.query<ILogItem[], TRequestLogsParams>({
            query: ({ project_name, ...body }) => {
                return {
                    url: API.PROJECTS.LOGS(project_name),
                    method: 'POST',
                    body,
                };
            },

            keepUnusedDataFor: 0,
            providesTags: () => ['ProjectLogs'],
            transformResponse: (response: { logs: ILogItem[] }) =>
                response.logs.map((logItem) => ({
                    ...logItem,
                    message: base64ToArrayBuffer(logItem.message as string),
                })),
        }),

        getProjectRepos: builder.query<IRepo[], { project_name: string }>({
            query: ({ project_name }) => {
                return {
                    url: API.PROJECTS.REPOS_LIST(project_name),
                    method: 'POST',
                };
            },

            providesTags: () => ['ProjectRepos'],
        }),
    }),
});

export const {
    useGetProjectsQuery,
    useGetProjectQuery,
    useCreateProjectMutation,
    useUpdateProjectMembersMutation,
    useDeleteProjectsMutation,
    useGetProjectLogsQuery,
    useGetProjectReposQuery,
} = projectApi;
