import { createApi, BaseQueryFn, FetchBaseQueryError } from '@reduxjs/toolkit/query/react';
import cloudWatchLogsInterface from 'libs/cloudWatchLogsInterface';

export const awsLogQuery = async (
    params: IAWSFilterLogEventsRequestParams,
): Promise<{ data: unknown } | { error: { data: unknown } }> => {
    try {
        const data = await cloudWatchLogsInterface.filterLogEvents(params);

        return { data };
    } catch (error) {
        return { error: { data: error } };
    }
};

export const awsLogsBaseQuery = (): BaseQueryFn<IAWSFilterLogEventsRequestParams, unknown, unknown> =>
    awsLogQuery as BaseQueryFn;

export const awsLogsApi = createApi({
    reducerPath: 'awsLogsApi',
    baseQuery: awsLogsBaseQuery(),

    tagTypes: ['AWS'],

    endpoints: (builder) => ({
        getRuntimeLogs: builder.query<IAWSFilterLogEventsResponse, IAWSFilterLogEventsRequestParams>({
            async queryFn(_arg) {
                try {
                    const data = await cloudWatchLogsInterface.filterLogEvents(_arg);
                    return { data };
                } catch (error) {
                    return { error: { data: error } as FetchBaseQueryError };
                }
            },
            providesTags: [{ type: 'AWS' }],
        }),

        getOldLogsQueryId: builder.query<IAWSStartQueryResponse, IAWSStartQueryRequestParams>({
            async queryFn(_arg) {
                try {
                    const data = await cloudWatchLogsInterface.startQuery(_arg);
                    return { data };
                } catch (error) {
                    return { error: { data: error } as FetchBaseQueryError };
                }
            },
            providesTags: [{ type: 'AWS' }],
        }),

        getLogsByQueryId: builder.query<IAWSQueryResponse, IAWSQueryRequestParams>({
            async queryFn(_arg) {
                try {
                    const data = await cloudWatchLogsInterface.query(_arg);
                    return { data };
                } catch (error) {
                    return { error: { data: error } as FetchBaseQueryError };
                }
            },
            providesTags: [{ type: 'AWS' }],
        }),
    }),
});

export const { useGetRuntimeLogsQuery, useGetOldLogsQueryIdQuery } = awsLogsApi;
