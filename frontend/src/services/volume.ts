import { API } from 'api';
import { createApi } from '@reduxjs/toolkit/query/react';
import { fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const volumeApi = createApi({
    reducerPath: 'volumeApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Volumes'],

    endpoints: (builder) => ({
        getAllVolumes: builder.query<IVolume[], TVolumesListRequestParams | void>({
            query: (body) => {
                return {
                    url: API.VOLUME.LIST(),
                    method: 'POST',
                    body,
                };
            },

            providesTags: (result) =>
                result ? [...result.map(({ id }) => ({ type: 'Volumes' as const, id: id })), 'Volumes'] : ['Volumes'],
        }),
    }),
});

export const { useLazyGetAllVolumesQuery } = volumeApi;
