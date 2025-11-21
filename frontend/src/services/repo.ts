import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

import { TGetRepoResponse, TInitRepoRequestParams } from '../types/repo';

export const repoApi = createApi({
    reducerPath: 'repoApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Repos'],

    endpoints: (builder) => ({
        getRepo: builder.query<TGetRepoResponse, { project_name: string; repo_id: string; include_creds: boolean }>({
            query: ({ project_name, ...body }) => {
                return {
                    url: API.PROJECTS.GET_REPO(project_name),
                    body,
                    method: 'POST',
                };
            },

            providesTags: (result) => (result ? [{ type: 'Secrets' as const, id: result.repo_id }, 'Repos'] : ['Repos']),
        }),

        initRepo: builder.mutation<string, { project_name: IProject['project_name'] } & TInitRepoRequestParams>({
            query: ({ project_name, ...body }) => ({
                url: API.PROJECTS.INIT_REPO(project_name),
                method: 'POST',
                body,
            }),

            invalidatesTags: () => ['Secrets'],
        }),
    }),
});

export const { useLazyGetRepoQuery, useInitRepoMutation } = repoApi;
