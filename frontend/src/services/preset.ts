import { useSelector } from 'react-redux';
import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

import { selectAuthToken } from 'App/slice';

// The viewer is part of the client cache key, never the API request body.
export type PresetListQueryArgs = TPresetsListRequestParams & { authToken?: string };
type PresetQueryArgs = { project_name: IProject['project_name']; id: IPreset['id']; authToken?: string };

export const presetApi = createApi({
    reducerPath: 'presetApi',
    refetchOnMountOrArgChange: true,
    baseQuery: fetchBaseQuery({
        prepareHeaders: (headers, api) => {
            if (api.endpoint === 'getAllPresets' || api.endpoint === 'getPreset') {
                headers.set('X-API-VERSION', 'latest');
                return headers;
            }
            return fetchBaseQueryHeaders(headers, api);
        },
    }),

    tagTypes: ['Presets'],

    endpoints: (builder) => ({
        getAllPresets: builder.query<IPreset[], PresetListQueryArgs>({
            query: ({ authToken, ...body }) => ({
                url: API.PRESET.LIST(),
                method: 'POST',
                headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
                body,
            }),

            transformResponse: (response: IPresetListResponse) => response.presets,

            providesTags: (result) =>
                result ? [...result.map(({ id }) => ({ type: 'Presets' as const, id })), 'Presets'] : ['Presets'],
        }),

        getPreset: builder.query<IPresetDetails, PresetQueryArgs>({
            query: ({ project_name, id, authToken }) => ({
                url: API.PROJECTS.PRESETS_GET(project_name),
                method: 'POST',
                headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
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

export const { useLazyGetAllPresetsQuery, useDeletePresetMutation } = presetApi;

export const useGetPresetQuery = (args: Omit<PresetQueryArgs, 'authToken'>) => {
    const authToken = useSelector(selectAuthToken);
    return presetApi.useGetPresetQuery({ ...args, authToken });
};
