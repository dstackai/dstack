import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import { base64ToArrayBuffer } from 'libs';
import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

const decoder = new TextDecoder('utf-8');

// Helper function to transform backend response to frontend format
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const transformProjectResponse = (project: any): IProject => ({
    ...project,
    isPublic: project.is_public,
});

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

            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            transformResponse: (response: any[]): IProject[] => response.map(transformProjectResponse),

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

            transformResponse: transformProjectResponse,

            providesTags: (result) => (result ? [{ type: 'Projects' as const, id: result.project_name }] : []),
        }),

        createProject: builder.mutation<IProject, IProject>({
            query: (project) => ({
                url: API.PROJECTS.CREATE(),
                method: 'POST',
                body: project,
            }),

            transformResponse: transformProjectResponse,

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

            transformResponse: transformProjectResponse,

            invalidatesTags: (result, error, params) => [{ type: 'Projects' as const, id: params?.project_name }],
        }),

        addProjectMember: builder.mutation<IProject, { project_name: string; username: string; project_role?: string }>({
            query: ({ project_name, username, project_role = 'user' }) => ({
                url: API.PROJECTS.ADD_MEMBERS(project_name),
                method: 'POST',
                body: {
                    members: [{ username, project_role }],
                },
            }),

            transformResponse: transformProjectResponse,

            invalidatesTags: (result, error, params) => [{ type: 'Projects' as const, id: params?.project_name }],
        }),

        removeProjectMember: builder.mutation<IProject, { project_name: string; username: string }>({
            query: ({ project_name, username }) => ({
                url: API.PROJECTS.REMOVE_MEMBERS(project_name),
                method: 'POST',
                body: {
                    usernames: [username],
                },
            }),

            transformResponse: transformProjectResponse,

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

        getProjectLogs: builder.query<TResponseLogsParams, TRequestLogsParams>({
            query: ({ project_name, ...body }) => {
                return {
                    url: API.PROJECTS.LOGS(project_name),
                    method: 'POST',
                    body,
                };
            },

            keepUnusedDataFor: 0,
            providesTags: () => ['ProjectLogs'],
            transformResponse: (response: { logs: ILogItem[]; next_token: string }) => {
                const logs = response.logs.map((logItem) => ({
                    ...logItem,
                    message: decoder.decode(base64ToArrayBuffer(logItem.message)),
                }));

                return {
                    ...response,
                    logs,
                };
            },
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

        updateProject: builder.mutation<IProject, { project_name: string; is_public: boolean }>({
            query: ({ project_name, is_public }) => ({
                url: API.PROJECTS.UPDATE(project_name),
                method: 'POST',
                body: { is_public },
            }),
            transformResponse: transformProjectResponse,
            invalidatesTags: (result, error, params) => [{ type: 'Projects' as const, id: params?.project_name }],
        }),
    }),
});

export const {
    useGetProjectsQuery,
    useGetProjectQuery,
    useCreateProjectMutation,
    useUpdateProjectMembersMutation,
    useAddProjectMemberMutation,
    useRemoveProjectMemberMutation,
    useDeleteProjectsMutation,
    useGetProjectLogsQuery,
    useLazyGetProjectLogsQuery,
    useGetProjectReposQuery,
    useUpdateProjectMutation,
} = projectApi;
