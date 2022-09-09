import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';
import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const tagsApi = createApi({
    reducerPath: 'tagsApi',
    baseQuery: fetchBaseQuery({
        baseUrl: process.env.API_URL,
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Tags'],

    endpoints: (builder) => ({
        getTags: builder.query<ITag[], TFetchTagsRequestParams>({
            query: (params) => {
                return {
                    url: `/tags/query?${new URLSearchParams({
                        repo_user_name: params.repoUserName,
                        repo_name: params.repoName,
                    }).toString()}`,
                };
            },

            transformResponse: (response: { tags: ITag[] }) => response.tags,

            providesTags: (result) =>
                result
                    ? [...result.map(({ tag_name }) => ({ type: 'Tags', id: tag_name } as const)), { type: 'Tags', id: 'LIST' }]
                    : [{ type: 'Tags', id: 'LIST' }],
        }),

        getTag: builder.query<ITag, TFetchTagRequestParams>({
            query: (params) => {
                return {
                    url: `/tags/get?${new URLSearchParams({
                        repo_user_name: params.repoUserName,
                        repo_name: params.repoName,
                        tag_name: params.tagName,
                    }).toString()}`,
                };
            },

            transformResponse: (response: { tag: ITag }) => response.tag,
            providesTags: (result, error, { tagName }) => [{ type: 'Tags', id: tagName }],
        }),

        add: builder.mutation<void, TAddTagRequestParams>({
            query: (body) => {
                return {
                    url: `/tags/add`,
                    method: 'POST',
                    body,
                };
            },

            invalidatesTags: () => [{ type: 'Tags', id: 'LIST' }],
        }),

        delete: builder.mutation<void, TDeleteTagRequestParams>({
            query: (body) => {
                return {
                    url: `/tags/delete`,
                    method: 'POST',
                    body,
                };
            },

            invalidatesTags: (result, error, { tagName }) => [
                { type: 'Tags', id: tagName },
                { type: 'Tags', id: 'LIST' },
            ],
        }),
    }),
});

export const { useGetTagsQuery, useDeleteMutation, useAddMutation } = tagsApi;
