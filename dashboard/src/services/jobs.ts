import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';
import fetchBaseQueryHeaders from 'libs/fetchBaseQueryHeaders';

export const jobApi = createApi({
    reducerPath: 'jobApi',
    baseQuery: fetchBaseQuery({
        baseUrl: process.env.API_URL,
        prepareHeaders: fetchBaseQueryHeaders,
    }),

    tagTypes: ['Jobs'],

    endpoints: (builder) => ({
        getJobs: builder.query<IJob[], IJobsFetchParams>({
            query: (params) => {
                return {
                    url: `/jobs/query/?${new URLSearchParams({
                        n: params.count.toString(),
                        ...(params.repoUrl && { repo_url: params.repoUrl }),
                        ...(params.runName && { run_name: params.runName }),
                        ...(params.userName && { user_name: params.userName }),
                        ...(params.workflowName && { workflow_name: params.workflowName }),
                    }).toString()}`,
                };
            },
            transformResponse: (response: { jobs: IJob[] }) => response.jobs,

            providesTags: (result) =>
                result
                    ? [...result.map(({ job_id }) => ({ type: 'Jobs', id: job_id } as const)), { type: 'Jobs', id: 'LIST' }]
                    : [{ type: 'Jobs', id: 'LIST' }],
        }),

        getJob: builder.query<IJob, IJob['job_id']>({
            query: (id) => {
                return {
                    url: `/jobs/${id}`,
                };
            },
            providesTags: (result, error, id) => [{ type: 'Jobs', id }],
            transformResponse: (response: { job: IJob }) => response.job,
        }),

        resumeJob: builder.mutation<void, Pick<IJob, 'job_id'>>({
            query: (body) => {
                return {
                    url: `/jobs/resume`,
                    method: 'POST',
                    body,
                };
            },
            invalidatesTags: (result, error, { job_id }) => [{ type: 'Jobs', id: job_id }],
        }),

        stopJob: builder.mutation<void, Pick<IJob, 'job_id'> & { abort?: boolean }>({
            query: (body) => {
                return {
                    url: `/jobs/stop`,
                    method: 'POST',
                    body,
                };
            },
            invalidatesTags: (result, error, { job_id }) => [{ type: 'Jobs', id: job_id }],
        }),

        refetchJobs: builder.mutation<null, void>({
            queryFn: () => ({ data: null }),
            invalidatesTags: [{ type: 'Jobs', id: 'LIST' }],
        }),

        refetchJob: builder.mutation<null, IJob['job_id']>({
            queryFn: () => ({ data: null }),
            invalidatesTags: (result, error, jobId) => [{ type: 'Jobs', id: jobId }],
        }),
    }),
});

export const {
    useGetJobsQuery,
    useResumeJobMutation,
    useStopJobMutation,
    useGetJobQuery,
    useRefetchJobsMutation,
    useRefetchJobMutation,
} = jobApi;
