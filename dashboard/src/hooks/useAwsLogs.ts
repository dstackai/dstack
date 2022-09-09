import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useGetOldLogsQueryIdQuery, useGetRuntimeLogsQuery } from 'services/awsLogs';
import { awsLogEventToString, awsQueryResulToString } from 'libs/aws';
import cloudWatchLogsInterface from '../libs/cloudWatchLogsInterface';
import { getDateFewDaysAgo } from '../libs';
import { useIsMounted } from './index';

interface Options {
    pollingInterval?: number;
}

interface IAWSFilterLogEventsResponseFormatted {
    logs: string[];
    nextToken: string;
    lastEventTimestamp?: number;
}

const transformResponse = (response: IAWSFilterLogEventsResponse): IAWSFilterLogEventsResponseFormatted => {
    return {
        logs: response.events.map(awsLogEventToString),
        nextToken: response.nextToken,
        lastEventTimestamp: response.events[response.events.length - 1]?.timestamp,
    };
};

function useAwsLogs<T extends HTMLElement = HTMLElement>(
    ref: React.RefObject<T>,
    params: IAWSFilterLogEventsRequestParams,
    { pollingInterval = 1000 }: Options,
) {
    const [isLoading, setIsLoading] = useState<boolean>(true);
    const [isLoadingOldLogs, setIsLoadingOldLogs] = useState<boolean>(false);
    const [logs, setLogs] = useState<string[]>([]);
    const timeout = useRef<ReturnType<typeof setTimeout> | null>(null);
    const pollOldLogsTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
    const lastEventTimestamp = useRef<number>(params.startTime);
    const lastNextToken = useRef<string>();
    const isUpdateScrollPosition = useRef<boolean>(true);
    const lastQueryId = useRef<string | null>(null);
    const jobId = params?.logStreamNames?.[0];
    const isMounted = useIsMounted();

    const { data: logsResponse, isLoading: isLoadingRuntimeLogs } = useGetRuntimeLogsQuery(params, {
        skip: !params.region || !params.accessKeyId || !params.secretAccessKey || !params.logGroupName,
    });

    const { data: queryIdData, isLoading: isLoadingOldLogsQuery } = useGetOldLogsQueryIdQuery(
        {
            region: params.region,
            accessKeyId: params.accessKeyId,
            secretAccessKey: params.secretAccessKey,
            logGroupName: params.logGroupName,
            endTime: params.startTime - 1,
            limit: 10000,
            queryString: `fields @logStream, @timestamp, log | sort @timestamp asc${
                jobId ? ` | filter @logStream = "${jobId}"` : ''
            }`,
            startTime: getDateFewDaysAgo(10, params.startTime),
        },
        {
            skip: !params.region || !params.accessKeyId || !params.secretAccessKey || !params.logGroupName,
        },
    );

    useEffect(() => {
        setIsLoading((isLoadingRuntimeLogs || isLoadingOldLogsQuery || isLoadingOldLogs) && !logs.length);
    }, [isLoadingRuntimeLogs, isLoadingOldLogsQuery, isLoadingOldLogs, logs]);

    const getMoreLogs = async () => {
        try {
            const response = await cloudWatchLogsInterface.filterLogEvents({
                ...params,
                startTime: lastEventTimestamp.current,
                nextToken: lastNextToken.current,
            });

            const { logs, lastEventTimestamp: lastTimestamp, nextToken } = transformResponse(response);

            lastNextToken.current = nextToken;

            if (lastTimestamp) {
                lastEventTimestamp.current = lastTimestamp + 1;
            }

            checkNeedScrollToBottom();
            setLogs((old) => [...old, ...logs]);
        } catch (error) {
            console.log(error);
        }

        if (isMounted()) timeout.current = setTimeout(getMoreLogs, pollingInterval);
    };

    const checkLoadingOldLogs = async () => {
        if (!lastQueryId.current) {
            setIsLoadingOldLogs(false);
            return;
        }

        try {
            const response = await cloudWatchLogsInterface.query({
                region: params.region,
                accessKeyId: params.accessKeyId,
                secretAccessKey: params.secretAccessKey,
                queryId: lastQueryId.current,
            });

            if (isMounted()) {
                if (response.status === 'Running')
                    pollOldLogsTimeout.current = setTimeout(checkLoadingOldLogs, pollingInterval);
                else {
                    const oldLogs = response.results.map(awsQueryResulToString);
                    setIsLoadingOldLogs(false);
                    checkNeedScrollToBottom();
                    setLogs((current) => [...oldLogs, ...current]);
                }
            }
        } catch (error) {
            if (isMounted()) pollOldLogsTimeout.current = setTimeout(checkLoadingOldLogs, pollingInterval);
            console.log(error);
        }
    };

    useEffect(() => {
        if (timeout.current !== null) clearTimeout(timeout.current);
        if (pollOldLogsTimeout.current !== null) clearTimeout(pollOldLogsTimeout.current);
        setLogs([]);

        return () => {
            if (timeout.current !== null) clearTimeout(timeout.current);
            if (pollOldLogsTimeout.current !== null) clearTimeout(pollOldLogsTimeout.current);
        };
    }, [params.region, params.accessKeyId, params.secretAccessKey, params.logGroupName, jobId, params.startTime]);

    useEffect(() => {
        if (logsResponse) {
            const { logs, lastEventTimestamp: lastTimestamp, nextToken } = transformResponse(logsResponse);

            setLogs(logs);
            lastNextToken.current = nextToken;

            if (lastTimestamp) {
                lastEventTimestamp.current = lastTimestamp + 1;
            }

            timeout.current = setTimeout(getMoreLogs, pollingInterval);
        }
    }, [logsResponse]);

    useEffect(() => {
        if (queryIdData) {
            const { queryId } = queryIdData;
            lastQueryId.current = queryId;

            if (queryId) {
                pollOldLogsTimeout.current = setTimeout(checkLoadingOldLogs, pollingInterval);
                setIsLoadingOldLogs(true);
            }
        }
    }, [queryIdData]);

    useLayoutEffect(() => {
        if (ref.current) {
            if (isUpdateScrollPosition.current) scrollToBottom();
        }
    }, [logs]);

    const checkNeedScrollToBottom = () => {
        if (!ref.current) {
            isUpdateScrollPosition.current = false;
            return;
        }

        const { clientHeight, scrollHeight, scrollTop } = ref.current;
        isUpdateScrollPosition.current = scrollHeight - clientHeight <= scrollTop + 20;
    };

    const scrollToBottom = () => {
        if (!ref.current) return;

        const { clientHeight, scrollHeight } = ref.current;
        ref.current.scrollTo(0, scrollHeight - clientHeight);
    };

    return { logs, isLoading };
}

export default useAwsLogs;
