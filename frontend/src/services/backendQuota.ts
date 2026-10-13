import { API } from 'api';

import { projectApi } from './project';

export const backendQuotaApi = projectApi.injectEndpoints({
    endpoints: (builder) => ({
        getBackendQuotas: builder.query<IBackendQuota[], { projectName: string; backendName: TBackendType }>({
            query: ({ projectName, backendName }) => ({
                url: API.PROJECT_BACKENDS.QUOTAS(projectName, backendName),
                method: 'POST',
            }),
            providesTags: (result, error, { projectName }) => [{ type: 'Backends', id: `${projectName}/quota` }],
        }),
    }),
});

export const { useGetBackendQuotasQuery } = backendQuotaApi;
