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
        getFleets: builder.query<IFleet[], { projectName: IProject['project_name'] }>({
            query: ({ projectName }) => {
                return {
                    url: API.PROJECTS.FLEETS(projectName),
                    method: 'POST',
                };
            },

            providesTags: (result) =>
                result ? [...result.map(({ name }) => ({ type: 'Fleet' as const, id: name })), 'Fleets'] : ['Fleets'],
        }),
    }),
});

export const { useGetFleetsQuery } = fleetApi;
