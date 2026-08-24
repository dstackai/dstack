import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const presetApi = createApi({
    reducerPath: 'presetApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Presets'],

    endpoints: (builder) => ({
        getAllPresets: builder.query<IPreset[], TPresetsListRequestParams>({
            query: (body) => ({
                url: API.PRESET.LIST(),
                method: 'POST',
                body,
            }),

            transformResponse: (response: IPresetListResponse) => response.presets,

            providesTags: (result) =>
                result ? [...result.map(({ id }) => ({ type: 'Presets' as const, id })), 'Presets'] : ['Presets'],
        }),

        getPreset: builder.query<IPresetDetails, { project_name: IProject['project_name']; id: IPreset['id'] }>({
            query: ({ project_name, id }) => ({
                url: API.PROJECTS.PRESETS_GET(project_name),
                method: 'POST',
                body: { name_or_id: id },
            }),

            providesTags: (result) => (result ? [{ type: 'Presets' as const, id: result.id }] : []),
        }),

        deletePreset: builder.mutation<void, { project_name: IProject['project_name']; id: IPreset['id'] }>({
            query: ({ project_name, id }) => ({
                url: API.PROJECTS.PRESETS_DELETE(project_name),
                method: 'POST',
                body: { id },
            }),

            invalidatesTags: ['Presets'],
        }),
    }),
});

export const { useLazyGetAllPresetsQuery, useGetPresetQuery, useDeletePresetMutation } = presetApi;
