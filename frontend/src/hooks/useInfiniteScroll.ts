/* eslint-disable @typescript-eslint/no-explicit-any */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { UseLazyQuery /*, UseQueryStateOptions*/ } from '@reduxjs/toolkit/dist/query/react/buildHooks';
import { QueryDefinition } from '@reduxjs/toolkit/query';

const SCROLL_POSITION_GAP = 400;

type InfinityListArgs = Partial<Record<string, unknown>>;

type ListResponse<DataItem> = DataItem[];

type UseInfinityParams<DataItem, Args extends InfinityListArgs> = {
    useLazyQuery: UseLazyQuery<QueryDefinition<Args, any, any, ListResponse<DataItem>, any>>;
    args: { limit?: number } & Args;
    getPaginationParams: (listItem: DataItem) => Partial<Args>;
    // options?: UseQueryStateOptions<QueryDefinition<Args, any, any, Data[], any>, Record<string, any>>;
};

export const useInfiniteScroll = <DataItem, Args extends InfinityListArgs>({
    useLazyQuery,
    getPaginationParams,
    // options,
    args,
}: UseInfinityParams<DataItem, Args>) => {
    const [data, setData] = useState<ListResponse<DataItem>>([]);
    const scrollElement = useRef<HTMLElement>(document.documentElement);
    const isLoadingRef = useRef<boolean>(false);
    const lastRequestParams = useRef<TRunsRequestParams | undefined>(undefined);
    const [disabledMore, setDisabledMore] = useState(false);
    const { limit, ...argsProp } = args;

    const [getItems, { isLoading, isFetching }] = useLazyQuery({ ...args } as Args);

    const getDataRequest = (params: Args) => {
        lastRequestParams.current = params;

        return getItems({
            limit,
            ...params,
        } as Args).unwrap();
    };

    const getEmptyList = () => {
        isLoadingRef.current = true;

        setData([]);

        getDataRequest(argsProp as Args).then((result) => {
            setDisabledMore(false);
            setData(result as ListResponse<DataItem>);
            isLoadingRef.current = false;
        });
    };

    useEffect(() => {
        getEmptyList();
    }, Object.values(argsProp));

    const getMore = async () => {
        if (isLoadingRef.current || disabledMore) {
            return;
        }

        try {
            isLoadingRef.current = true;

            const result = await getDataRequest({
                ...argsProp,
                ...getPaginationParams(data[data.length - 1]),
            } as Args);

            if (result.length > 0) {
                setData((prev) => [...prev, ...result]);
            } else {
                setDisabledMore(true);
            }
        } catch (e) {
            console.log(e);
        }

        isLoadingRef.current = false;
    };

    useLayoutEffect(() => {
        const element = scrollElement.current;

        if (isLoadingRef.current || !data.length) return;

        if (element.scrollHeight - element.clientHeight <= 0) {
            getMore().catch(console.log);
        }
    }, [data]);

    const onScroll = useCallback(() => {
        if (disabledMore || isLoadingRef.current) {
            return;
        }

        const element = scrollElement.current;

        const scrollPositionFromBottom = element.scrollHeight - (element.clientHeight + element.scrollTop);

        if (scrollPositionFromBottom < SCROLL_POSITION_GAP) {
            getMore().catch(console.log);
        }
    }, [disabledMore, getMore]);

    useEffect(() => {
        document.addEventListener('scroll', onScroll);

        return () => {
            document.removeEventListener('scroll', onScroll);
        };
    }, [onScroll]);

    const isLoadingMore = data.length > 0 && isFetching;

    return {
        data,
        isLoading: isLoading || (data.length === 0 && isFetching),
        isLoadingMore,
        refreshList: getEmptyList,
    } as const;
};
