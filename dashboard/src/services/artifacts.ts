import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';
import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const artifactsApi = createApi({
    reducerPath: 'artifactsApi',
    baseQuery: fetchBaseQuery({
        baseUrl: process.env.API_URL,
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Artifacts'],

    endpoints: (builder) => ({
        getArtifactObjects: builder.query<IArtifactObject[], IArtifactsFetchParams>({
            query: (params) => {
                const { ...searchParams } = params;

                const nonNullSearchParams = Object.fromEntries(Object.entries(searchParams).filter(([_, v]) => v != null));

                return {
                    url: `/artifacts/browse?${new URLSearchParams(
                        nonNullSearchParams as unknown as URLSearchParams,
                    ).toString()}`,
                };
            },

            transformResponse: (response: { objects: IArtifactObject[] }) => response.objects,
        }),
    }),
});

export const { useGetArtifactObjectsQuery } = artifactsApi;
