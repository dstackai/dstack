import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';
import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const onDemandApi = createApi({
    reducerPath: 'onDemandApi',
    baseQuery: fetchBaseQuery({
        baseUrl: process.env.API_URL,
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Settings', 'Limits'],

    endpoints: (builder) => ({
        getRegions: builder.query<IRegion[], void>({
            query: () => {
                return {
                    url: '/on-demand/regions',
                    method: 'POST',
                };
            },

            transformResponse: (response: { regions: IRegion[] }) => response.regions,
        }),

        getLimits: builder.query<ILimit[], void>({
            query: () => {
                return {
                    url: '/on-demand/limits/query',
                    method: 'GET',
                };
            },
            providesTags: [{ type: 'Limits' }],
            transformResponse: (response: { limits: ILimit[] }) => response.limits,
        }),

        getInstanceTypes: builder.query<IInstanceType[], IInstanceTypesRequestParams>({
            query: (body) => {
                return {
                    url: '/on-demand/instance-types',
                    method: 'POST',
                    body,
                };
            },

            transformResponse: (response: { instance_types: IInstanceType[] }) => response.instance_types,
        }),

        getSettings: builder.query<IDemandSettings, void>({
            query: () => {
                return {
                    url: '/on-demand/settings',
                    method: 'POST',
                };
            },

            providesTags: [{ type: 'Settings' }],
        }),

        setLimit: builder.mutation<void, ISetLimitRequestParams>({
            query: (body) => {
                return {
                    url: '/on-demand/limits/set',
                    method: 'POST',
                    body,
                };
            },
            invalidatesTags: [{ type: 'Limits' }],
        }),

        deleteLimit: builder.mutation<void, IDeleteLimitRequestParams>({
            query: (body) => {
                return {
                    url: '/on-demand/limits/delete',
                    method: 'POST',
                    body,
                };
            },
            invalidatesTags: [{ type: 'Limits' }],
        }),

        updateSettings: builder.mutation<void, Partial<IDemandSettings>>({
            query: (body) => {
                return {
                    url: '/on-demand/settings/update',
                    method: 'POST',
                    body,
                };
            },
            invalidatesTags: [{ type: 'Settings' }],
        }),
    }),
});

export const {
    useGetRegionsQuery,
    useGetSettingsQuery,
    useUpdateSettingsMutation,
    useGetLimitsQuery,
    useGetInstanceTypesQuery,
    useSetLimitMutation,
    useDeleteLimitMutation,
} = onDemandApi;
