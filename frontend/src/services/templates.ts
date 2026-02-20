import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const templateApi = createApi({
    reducerPath: 'templateApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Templates'],

    endpoints: (builder) => ({
        getAllTemplates: builder.query<ITemplate[], { projectName: IProject['project_name'] }>({
            query: ({ projectName, ...body }) => {
                return {
                    url: API.PROJECTS.TEMPLATES_LIST(projectName),
                    method: 'POST',
                    body,
                };
            },

            providesTags: (result) =>
                result ? [...result.map(({ id }) => ({ type: 'Templates' as const, id: id })), 'Templates'] : ['Templates'],
        }),
    }),
});

export const { useGetAllTemplatesQuery } = templateApi;
