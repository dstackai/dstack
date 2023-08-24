import { API } from 'api';
import { createApi } from '@reduxjs/toolkit/query/react';
import { fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const gatewayApi = createApi({
    reducerPath: 'gatewayApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Gateways', 'Backends'],

    endpoints: (builder) => ({
        getProjectGateways: builder.query<IGateway[], { projectName: IProject['project_name'] }>({
            query: ({ projectName }) => ({
                url: API.PROJECT_GATEWAYS.BASE(projectName),
                method: 'GET',
            }),

            providesTags: (result) =>
                result
                    ? [...result.map((gateway) => ({ type: 'Gateways' as const, id: gateway.head.instance_name })), 'Gateways']
                    : ['Gateways'],
        }),

        getProjectGatewayBackends: builder.query<TGatewayBackendsListResponse, { projectName: IProject['project_name'] }>({
            query: ({ projectName }) => ({
                url: API.PROJECT_GATEWAYS.LIST_BACKENDS(projectName),
                method: 'GET',
            }),

            providesTags: ['Backends'],
        }),

        createProjectGateway: builder.mutation<
            IGateway,
            { projectName: IProject['project_name']; gateway: TCreateGatewayParams }
        >({
            query: ({ projectName, gateway }) => ({
                url: API.PROJECT_GATEWAYS.CREATE(projectName),
                method: 'POST',
                body: gateway,
            }),

            invalidatesTags: () => ['Gateways'],
        }),
    }),
});

export const { useGetProjectGatewaysQuery, useGetProjectGatewayBackendsQuery, useCreateProjectGatewayMutation } = gatewayApi;
