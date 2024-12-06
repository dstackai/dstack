import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const gatewayApi = createApi({
    reducerPath: 'gatewayApi',
    refetchOnMountOrArgChange: true,
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Gateways', 'Backends'],

    endpoints: (builder) => ({
        getProjectGateways: builder.query<IGateway[], { projectName: IProject['project_name'] }>({
            query: ({ projectName }) => ({
                url: API.PROJECT_GATEWAYS.LIST(projectName),
                method: 'POST',
            }),

            providesTags: (result) =>
                result
                    ? [...result.map((gateway) => ({ type: 'Gateways' as const, id: gateway.name })), 'Gateways']
                    : ['Gateways'],
        }),

        getProjectGateway: builder.query<IGateway, { projectName: IProject['project_name']; instanceName: IGateway['name'] }>({
            query: ({ projectName, instanceName }) => ({
                url: API.PROJECT_GATEWAYS.DETAILS(projectName),
                method: 'POST',
                body: {
                    name: instanceName,
                },
            }),

            providesTags: (result) => (result ? [{ type: 'Gateways' as const, id: result.name }, 'Gateways'] : ['Gateways']),
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

        deleteProjectGateway: builder.mutation<void, { projectName: IProject['project_name']; names: string[] }>({
            query: ({ projectName, names }) => ({
                url: API.PROJECT_GATEWAYS.DELETE(projectName),
                method: 'POST',
                body: { names },
            }),

            invalidatesTags: () => ['Gateways'],
        }),

        setDefaultProjectGateway: builder.mutation<
            IGateway,
            {
                projectName: IProject['project_name'];
                name: IGateway['name'];
            }
        >({
            query: ({ projectName, name }) => ({
                url: API.PROJECT_GATEWAYS.SET_DEFAULT(projectName),
                method: 'POST',
                body: {
                    name,
                },
            }),

            invalidatesTags: (result, _, { name }) => [{ type: 'Gateways' as const, id: name }, 'Gateways'],
        }),

        setWildcardDomainOfGateway: builder.mutation<
            IGateway,
            {
                projectName: IProject['project_name'];
                name: IGateway['name'];
                wildcard_domain?: IGateway['wildcard_domain'];
            }
        >({
            query: ({ projectName, name, wildcard_domain }) => ({
                url: API.PROJECT_GATEWAYS.SET_WILDCARD_DOMAIN(projectName),
                method: 'POST',
                body: {
                    name,
                    wildcard_domain,
                },
            }),

            invalidatesTags: (result, _, { name }) => [{ type: 'Gateways' as const, id: name }, 'Gateways'],
        }),
    }),
});

export const {
    useGetProjectGatewaysQuery,
    useGetProjectGatewayQuery,
    useCreateProjectGatewayMutation,
    useDeleteProjectGatewayMutation,
    useSetDefaultProjectGatewayMutation,
    useSetWildcardDomainOfGatewayMutation,
} = gatewayApi;
