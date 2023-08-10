import { API } from 'api';
import { createApi } from '@reduxjs/toolkit/query/react';
import { fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const projectApi = createApi({
    reducerPath: 'projectApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Projects', 'ProjectRepos', 'ProjectLogs'],

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
                    url: API.PROJECTS.DETAILS(name),
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

            invalidatesTags: (result) => [{ type: 'Projects' as const, id: result?.project_name }],
        }),

        updateProject: builder.mutation<IProject, Partial<IProject> & Pick<IProject, 'project_name'>>({
            query: (project) => ({
                url: API.PROJECTS.DETAILS(project.project_name),
                method: 'PATCH',
                body: project,
            }),

            invalidatesTags: (result) => [{ type: 'Projects' as const, id: result?.project_name }],
        }),

        updateProjectMembers: builder.mutation<IProject, Pick<IProject, 'project_name' | 'members'>>({
            query: (project) => ({
                url: API.PROJECTS.MEMBERS(project.project_name),
                method: 'POST',
                body: project.members,
            }),

            invalidatesTags: (result, error, params) => [{ type: 'Projects' as const, id: params?.project_name }],
        }),

        deleteProjects: builder.mutation<void, IProject['project_name'][]>({
            query: (projectNames) => ({
                url: API.PROJECTS.BASE(),
                method: 'DELETE',
                body: {
                    projects: projectNames,
                },
            }),

            invalidatesTags: () => ['Projects'],
        }),

        //     Repos queries
        getProjectRepos: builder.query<IRepo[], { name: IProject['project_name'] }>({
            query: ({ name }) => {
                return {
                    url: API.PROJECTS.REPO_LIST(name),
                    method: 'POST',
                };
            },

            providesTags: () => ['ProjectRepos'],
        }),

        getProjectRepo: builder.query<IRepo, { name: IProject['project_name']; repo_id: IRepo['repo_id'] }>({
            query: ({ name, ...body }) => {
                return {
                    url: API.PROJECTS.REPO_ITEM(name),
                    method: 'POST',
                    body,
                };
            },

            providesTags: () => ['ProjectRepos'],
        }),

        deleteProjectRepo: builder.mutation<void, { name: IProject['project_name']; repo_ids: IRepo['repo_id'][] }>({
            query: ({ name, ...body }) => {
                return {
                    url: API.PROJECTS.DELETE_REPO(name),
                    method: 'POST',
                    body,
                };
            },

            invalidatesTags: () => ['ProjectRepos'],
        }),

        getProjectLogs: builder.query<ILogItem[], TRequestLogsParams>({
            query: ({ name, ...body }) => {
                return {
                    url: API.PROJECTS.LOGS(name),
                    method: 'POST',
                    body,
                };
            },

            keepUnusedDataFor: 0,
            providesTags: () => ['ProjectLogs'],
        }),
    }),
});

export const {
    useGetProjectsQuery,
    useGetProjectQuery,
    useCreateProjectMutation,
    useUpdateProjectMutation,
    useUpdateProjectMembersMutation,
    useDeleteProjectsMutation,
    useGetProjectReposQuery,
    useGetProjectRepoQuery,
    useDeleteProjectRepoMutation,
    useGetProjectLogsQuery,
} = projectApi;
