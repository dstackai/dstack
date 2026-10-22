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
                if (body?.group_by?.length) {
                    body.group_by = body.group_by.filter((g) => g !== 'gpu' && g !== 'cpu');
                }

                return {
                    url: API.PROJECTS.GPUS_LIST(project_name),
                    method: 'POST',
                    body: { ...body, reverse: true },
                };
            },

            providesTags: ['Gpus'],
        }),
        getOffers: builder.query<TOffersQueryResponse, TGpusListQueryParams>({
            query: ({ project_name, run_spec }) => ({
                url: API.PROJECTS.RUN_GET_PLAN(project_name),
                method: 'POST',
                body: { run_spec, full_offers: true, for_offers_only: true, reverse_offers: true, max_offers: 100 },
            }),
            transformResponse: (response: { job_plans: TOffersQueryResponse[] }) => response.job_plans[0],
            providesTags: ['Gpus'],
        }),
    }),
});

export const { useGetGpusListQuery, useLazyGetGpusListQuery, useGetOffersQuery } = gpuApi;
