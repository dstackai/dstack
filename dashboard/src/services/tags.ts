import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';
import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const tagsApi = createApi({
    reducerPath: 'tagsApi',
    baseQuery: fetchBaseQuery({
        baseUrl: process.env.API_URL,
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Tag'],

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
                    ? [...result.map(({ tag_name }) => ({ type: 'Tag', id: tag_name } as const)), { type: 'Tag', id: 'LIST' }]
                    : [{ type: 'Tag', id: 'LIST' }],
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
            providesTags: (result, error, { tagName }) => [{ type: 'Tag', id: tagName }],
        }),

        add: builder.mutation<void, TAddTagRequestParams>({
            query: (body) => {
                return {
                    url: `/tags/add`,
                    method: 'POST',
                    body,
                };
            },

            invalidatesTags: () => [{ type: 'Tag', id: 'LIST' }],
        }),

        delete: builder.mutation<void, TDeleteTagRequestParams>({
            query: (body) => {
                return {
                    url: `/tags/delete`,
                    method: 'POST',
                    body,
                };
            },

            invalidatesTags: (result, error, { tag_name }) => [
                { type: 'Tag', id: tag_name },
                { type: 'Tag', id: 'LIST' },
            ],
        }),

        refetchTag: builder.mutation<null, Pick<TFetchTagRequestParams, 'tagName'>>({
            queryFn: () => ({ data: null }),
            invalidatesTags: (result, error, { tagName }) => [{ type: 'Tag', id: tagName }],
        }),
    }),
});

export const { useGetTagsQuery, useGetTagQuery, useDeleteMutation, useAddMutation, useRefetchTagMutation } = tagsApi;
