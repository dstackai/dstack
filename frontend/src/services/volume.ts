import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const volumeApi = createApi({
    reducerPath: 'volumeApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Volumes'],

    endpoints: (builder) => ({
        getAllVolumes: builder.query<IVolume[], TVolumesListRequestParams>({
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

        deleteVolumes: builder.mutation<void, { project_name: IProject['project_name']; names: IVolume['name'][] }>({
            query: ({ project_name, names }) => ({
                url: API.PROJECTS.VOLUMES_DELETE(project_name),
                method: 'POST',
                body: {
                    names,
                },
            }),

            invalidatesTags: () => ['Volumes'],
        }),
    }),
});

export const { useLazyGetAllVolumesQuery, useDeleteVolumesMutation } = volumeApi;
