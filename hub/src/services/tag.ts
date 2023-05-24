import { API } from 'api';
import { createApi } from '@reduxjs/toolkit/query/react';
import { fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const tagApi = createApi({
    reducerPath: 'tagApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Tags'],

    endpoints: (builder) => ({
        getTags: builder.query<ITag[], TTagsRequestParams>({
            query: ({ project_name, ...body }) => {
                return {
                    url: API.PROJECTS.TAG_LIST(project_name),
                    method: 'POST',
                    body,
                };
            },

            providesTags: (result) =>
                result ? [...result.map(({ tag_name }) => ({ type: 'Tags' as const, id: tag_name })), 'Tags'] : ['Tags'],
        }),

        getTag: builder.query<ITag, TTagRequestParams>({
            query: ({ project_name, tag_name, ...body }) => {
                return {
                    url: API.PROJECTS.TAG_ITEM(project_name, tag_name),
                    method: 'POST',
                    body,
                };
            },

            providesTags: (result) => (result ? [{ type: 'Tags' as const, id: result.tag_name }] : []),
        }),
    }),
});

export const { useGetTagsQuery, useGetTagQuery } = tagApi;
