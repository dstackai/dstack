import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const exportApi = createApi({
    reducerPath: 'exportApi',
    refetchOnMountOrArgChange: true,
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    endpoints: (builder) => ({
        getProjectExports: builder.query<IExport[], { project_name: IProject['project_name'] }>({
            query: ({ project_name }) => ({
                url: API.PROJECTS.EXPORTS_LIST(project_name),
                method: 'POST',
            }),

            transformResponse: (response: { exports: IExport[] }) => response.exports,
        }),
    }),
});

export const { useGetProjectExportsQuery } = exportApi;
