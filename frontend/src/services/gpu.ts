import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const gpuApi = createApi({
    reducerPath: 'gpuApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Gpus'],

    endpoints: (builder) => ({
        getGpusList: builder.query<TGpusListQueryResponse, TGpusListQueryParams>({
            query: ({ project_name, ...body }) => {
                return {
                    url: API.PROJECTS.GPUS_LIST(project_name),
                    method: 'POST',
                    body,
                };
            },

            providesTags: ['Gpus'],
        }),
    }),
});

export const { useGetGpusListQuery } = gpuApi;
