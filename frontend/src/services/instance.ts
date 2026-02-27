import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const instanceApi = createApi({
    reducerPath: 'instanceApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Instance', 'Instances'],

    endpoints: (builder) => ({
        getInstances: builder.query<IInstance[], TInstanceListRequestParams>({
            query: (body) => {
                return {
                    url: API.INSTANCES.LIST(),
                    method: 'POST',
                    body,
                };
            },

            providesTags: (result) =>
                result ? [...result.map(({ name }) => ({ type: 'Instance' as const, id: name })), 'Instances'] : ['Instances'],
        }),

        getInstanceDetails: builder.query<IInstance, { projectName: string; instanceId: string }>({
            query: ({ projectName, instanceId }) => {
                return {
                    url: API.INSTANCES.DETAILS(projectName),
                    method: 'POST',
                    body: { id: instanceId },
                };
            },

            providesTags: (result) => (result ? [{ type: 'Instance' as const, id: result.name }] : []),
        }),

        deleteInstances: builder.mutation<
            void,
            { projectName: IProject['project_name']; fleetName: string; instancesNums: number[] }
        >({
            query: ({ projectName, fleetName, instancesNums }) => {
                return {
                    url: API.PROJECTS.FLEET_INSTANCES_DELETE(projectName),
                    method: 'POST',
                    body: { name: fleetName, instance_nums: instancesNums },
                };
            },

            invalidatesTags: ['Instances'],
        }),
    }),
});

export const { useLazyGetInstancesQuery, useGetInstanceDetailsQuery, useDeleteInstancesMutation } = instanceApi;
