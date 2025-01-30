import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const fleetApi = createApi({
    reducerPath: 'fleetApi',
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Fleet', 'Fleets'],

    endpoints: (builder) => ({
        getFleets: builder.query<IFleet[], TFleetListRequestParams>({
            query: (body) => {
                return {
                    url: API.FLEETS.LIST(),
                    method: 'POST',
                    body,
                };
            },

            providesTags: (result) =>
                result ? [...result.map(({ name }) => ({ type: 'Fleet' as const, id: name })), 'Fleets'] : ['Fleets'],
        }),

        getProjectFleets: builder.query<IFleet[], { projectName: IProject['project_name'] }>({
            query: ({ projectName }) => {
                return {
                    url: API.PROJECTS.FLEETS(projectName),
                    method: 'POST',
                };
            },

            providesTags: (result) =>
                result ? [...result.map(({ name }) => ({ type: 'Fleet' as const, id: name })), 'Fleets'] : ['Fleets'],
        }),

        getFleetDetails: builder.query<
            IFleet,
            { projectName: IProject['project_name']; fleetName?: IFleet['name']; fleetId?: IFleet['id'] }
        >({
            query: ({ projectName, fleetName, fleetId }) => {
                return {
                    url: API.PROJECTS.FLEETS_DETAILS(projectName),
                    method: 'POST',
                    body: {
                        name: fleetName,
                        id: fleetId,
                    },
                };
            },

            providesTags: (result) => (result ? [{ type: 'Fleet' as const, id: result.name }] : []),
        }),

        deleteFleet: builder.mutation<IFleet[], { projectName: IProject['project_name']; fleetNames: string[] }>({
            query: ({ projectName, fleetNames }) => {
                return {
                    url: API.PROJECTS.FLEETS_DELETE(projectName),
                    method: 'POST',
                    body: { names: fleetNames },
                };
            },

            invalidatesTags: ['Fleets'],
        }),
    }),
});

export const { useLazyGetFleetsQuery, useDeleteFleetMutation, useGetFleetDetailsQuery } = fleetApi;
