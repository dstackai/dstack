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

        getProjectGateway: builder.query<
            IGateway,
            { projectName: IProject['project_name']; instanceName: IGateway['head']['instance_name'] }
        >({
            query: ({ projectName, instanceName }) => ({
                url: API.PROJECT_GATEWAYS.DETAILS(projectName, instanceName),
                method: 'GET',
            }),

            providesTags: (result) =>
                result ? [{ type: 'Gateways' as const, id: result.head.instance_name }, 'Gateways'] : ['Gateways'],
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

        deleteProjectGateway: builder.mutation<IGateway, { projectName: IProject['project_name']; instance_names: string[] }>({
            query: ({ projectName, instance_names }) => ({
                url: API.PROJECT_GATEWAYS.DELETE(projectName),
                method: 'POST',
                body: { instance_names },
            }),

            invalidatesTags: () => ['Gateways'],
        }),

        updateProjectGateway: builder.mutation<
            IGateway,
            {
                projectName: IProject['project_name'];
                instanceName: IGateway['head']['instance_name'];
                values: TUpdateGatewayParams;
            }
        >({
            query: ({ projectName, instanceName, values }) => ({
                url: API.PROJECT_GATEWAYS.UPDATE(projectName, instanceName),
                method: 'POST',
                body: values,
            }),

            invalidatesTags: (result, _, { instanceName }) => [{ type: 'Gateways' as const, id: instanceName }, 'Gateways'],
        }),

        testProjectGatewayDomain: builder.mutation<
            IGateway,
            {
                projectName: IProject['project_name'];
                instanceName: IGateway['head']['instance_name'];
                domain: string;
            }
        >({
            query: ({ projectName, instanceName, domain }) => ({
                url: API.PROJECT_GATEWAYS.TEST_DOMAIN(projectName, instanceName),
                method: 'POST',
                body: { domain },
            }),
        }),
    }),
});

export const {
    useGetProjectGatewaysQuery,
    useGetProjectGatewayQuery,
    useGetProjectGatewayBackendsQuery,
    useCreateProjectGatewayMutation,
    useDeleteProjectGatewayMutation,
    useUpdateProjectGatewayMutation,
    useTestProjectGatewayDomainMutation,
} = gatewayApi;
