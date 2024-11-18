import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const artifactApi = createApi({
    reducerPath: 'artifactApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Artifacts'],

    endpoints: (builder) => ({
        getArtifacts: builder.query<IArtifact[], TRequestArtifactListParams>({
            query: ({ name, ...body }) => {
                return {
                    url: API.PROJECTS.ARTIFACTS(name),
                    method: 'POST',
                    body,
                };
            },

            providesTags: ['Artifacts'],
        }),
    }),
});

export const { useGetArtifactsQuery } = artifactApi;
