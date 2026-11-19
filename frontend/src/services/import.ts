import { API } from 'api';
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const importApi = createApi({
    reducerPath: 'importApi',
    refetchOnMountOrArgChange: true,
    baseQuery: fetchBaseQuery({
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    endpoints: (builder) => ({
        // One import list request for each of the projects. A list that failed is left out, so that the others show.
        // A failure is expected for a public project that the user owns without being its member
        getProjectsImports: builder.query<TProjectImports[], { project_names: IProject['project_name'][] }>({
            queryFn: async ({ project_names }, api, extraOptions, baseQuery) => {
                const results = await Promise.all(
                    project_names.map((projectName) =>
                        baseQuery({
                            url: API.PROJECTS.IMPORTS_LIST(projectName),
                            method: 'POST',
                        }),
                    ),
                );

                return {
                    data: results.flatMap(({ data }, index) =>
                        data ? [{ project_name: project_names[index], imports: (data as { imports: IImport[] }).imports }] : [],
                    ),
                };
            },

            // A page must not decide "Not Found" on an answer cached by an earlier visit
            keepUnusedDataFor: 0,
        }),
    }),
});

export const { useGetProjectsImportsQuery } = importApi;
