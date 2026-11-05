/* eslint-disable @typescript-eslint/no-explicit-any */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { isEqual } from 'lodash';
import { UseLazyQuery /*, UseQueryStateOptions*/ } from '@reduxjs/toolkit/dist/query/react/buildHooks';
import { QueryDefinition } from '@reduxjs/toolkit/query';

const SCROLL_POSITION_GAP = 400;

type InfinityListArgs = Partial<Record<string, unknown>>;

type ListResponse<DataItem> = DataItem[];
type ResponseWithDataProp<DataItem> = { data: ListResponse<DataItem>; total_count: number };

type LazyQueryResponse<DataItem> = ResponseWithDataProp<DataItem> | ListResponse<DataItem>;

type UseInfinityParams<DataItem, Args extends InfinityListArgs> = {
    useLazyQuery: UseLazyQuery<QueryDefinition<Args, any, any, LazyQueryResponse<DataItem>, any>>;
    args: { limit?: number } & Args;
    getResponseItems?: (listItem: DataItem) => Partial<Args>;
    getPaginationParams: (listItem: DataItem) => Partial<Args>;
    // Items starting from the first one matching isPastEnd are dropped and no more items are loaded.
    // Changing isPastEnd reloads the list, so it should be memoized.
    isPastEnd?: (listItem: DataItem) => boolean;
    skip?: boolean;
    // options?: UseQueryStateOptions<QueryDefinition<Args, any, any, Data[], any>, Record<string, any>>;
};

export const useInfiniteScroll = <DataItem, Args extends InfinityListArgs>({
    useLazyQuery,
    getPaginationParams,
    // options,
    args,
    isPastEnd,
    skip,
}: UseInfinityParams<DataItem, Args>) => {
    const [data, setData] = useState<ListResponse<DataItem>>([]);
    const [totalCount, setTotalCount] = useState<number | void>();
    const scrollElement = useRef<HTMLElement>(document.documentElement);
    const isLoadingRef = useRef<boolean>(false);
    const isDisabledMoreRef = useRef<boolean>(false);
    const lastRequestParams = useRef<Args | undefined>(undefined);
    const { limit, ...argsProp } = args;
    const lastArgsProps = useRef<Partial<Args> | null>(null);
    const lastIsPastEnd = useRef<typeof isPastEnd>(undefined);
    // Incremented on every list reset, so that responses to outdated requests can be ignored
    const requestGenerationRef = useRef<number>(0);

    const [getItems, { isLoading, isFetching, error }] = useLazyQuery({ ...args } as Args);

    const getDataRequest = async (params: Args, requestGeneration: number) => {
        const result = await getItems({
            limit,
            ...params,
        } as Args).unwrap();

        if (requestGeneration === requestGenerationRef.current) {
            lastRequestParams.current = { ...params };
        }

        return result;
    };

    const truncatePastEnd = (items: ListResponse<DataItem>): ListResponse<DataItem> => {
        const endIndex = isPastEnd ? items.findIndex(isPastEnd) : -1;

        if (endIndex === -1) {
            return items;
        }

        isDisabledMoreRef.current = true;
        return items.slice(0, endIndex);
    };

    const getEmptyList = () => {
        const requestGeneration = ++requestGenerationRef.current;
        isLoadingRef.current = true;

        setData([]);

        getDataRequest(argsProp as Args, requestGeneration)
            .then((result: LazyQueryResponse<DataItem>) => {
                if (requestGeneration !== requestGenerationRef.current) {
                    return;
                }

                isDisabledMoreRef.current = false;

                if ('data' in result) {
                    setData(truncatePastEnd(result.data as ListResponse<DataItem>));
                    setTotalCount(result.total_count);
                } else {
                    setData(truncatePastEnd(result as ListResponse<DataItem>));
                    setTotalCount();
                }
            })
            .catch(() => {
                if (requestGeneration !== requestGenerationRef.current) {
                    return;
                }

                isDisabledMoreRef.current = true;
            })
            .finally(() => {
                if (requestGeneration !== requestGenerationRef.current) {
                    return;
                }

                isLoadingRef.current = false;
            });
    };

    useEffect(() => {
        if ((!isEqual(argsProp, lastArgsProps.current) || isPastEnd !== lastIsPastEnd.current) && !skip) {
            getEmptyList();
            lastArgsProps.current = argsProp as Args;
            lastIsPastEnd.current = isPastEnd;
        }
    }, [argsProp, lastArgsProps, isPastEnd, skip]);

    const getMore = async () => {
        if (isLoadingRef.current || isDisabledMoreRef.current || skip || !data.length) {
            return;
        }

        const requestParams = {
            ...argsProp,
            ...getPaginationParams(data[data.length - 1]),
        };

        if (!isEqual(requestParams, lastRequestParams.current)) {
            const requestGeneration = requestGenerationRef.current;

            try {
                isLoadingRef.current = true;

                const result = await getDataRequest(requestParams as Args, requestGeneration);

                if (requestGeneration !== requestGenerationRef.current) {
                    return;
                }

                let listResponse: ListResponse<DataItem>;

                if ('data' in result) {
                    listResponse = truncatePastEnd(result.data);
                    setTotalCount(result.total_count);
                } else {
                    listResponse = truncatePastEnd(result);
                    setTotalCount();
                }

                if (listResponse.length > 0) {
                    setData((prev) => [...prev, ...listResponse]);
                } else {
                    isDisabledMoreRef.current = true;
                }
            } catch (e) {
                if (requestGeneration !== requestGenerationRef.current) {
                    return;
                }

                console.log(e);
            }

            setTimeout(() => {
                if (requestGeneration === requestGenerationRef.current) {
                    isLoadingRef.current = false;
                }
            }, 50);
        }
    };

    useLayoutEffect(() => {
        const element = scrollElement.current;

        if (isLoadingRef.current || !data.length) return;

        if (element.scrollHeight - element.clientHeight <= 0) {
            getMore().catch(console.log);
        }
    }, [data]);

    const onScroll = useCallback(() => {
        if (isDisabledMoreRef.current || isLoadingRef.current) {
            return;
        }

        const element = scrollElement.current;

        const scrollPositionFromBottom = element.scrollHeight - (element.clientHeight + element.scrollTop);

        if (scrollPositionFromBottom < SCROLL_POSITION_GAP) {
            getMore().catch(console.log);
        }
    }, [getMore]);

    useEffect(() => {
        document.addEventListener('scroll', onScroll);

        return () => {
            document.removeEventListener('scroll', onScroll);
        };
    }, [onScroll]);

    const isLoadingMore = data.length > 0 && isFetching;

    return {
        data,
        error,
        totalCount,
        isLoading: isLoading || (data.length === 0 && isFetching),
        isLoadingMore,
        refreshList: getEmptyList,
    } as const;
};
