import { useEffect, useRef, useState } from 'react';
import { orderBy as _orderBy } from 'lodash';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useLazyGetRunsQuery } from 'services/run';

export const useRunsData = ({ project_name, only_active }: TRunsRequestParams) => {
    const [data, setData] = useState<IRun[]>([]);
    const [pagesCount, setPagesCount] = useState<number>(1);
    const [disabledNext, setDisabledNext] = useState(false);
    const lastRequestParams = useRef<TRunsRequestParams | undefined>(undefined);

    const [getRuns, { isLoading, isFetching }] = useLazyGetRunsQuery();

    const getRunsRequest = (params?: Partial<TRunsRequestParams>) => {
        lastRequestParams.current = params;

        return getRuns({
            project_name,
            only_active,
            limit: DEFAULT_TABLE_PAGE_SIZE,
            ...params,
        }).unwrap();
    };

    const refreshList = () => {
        getRunsRequest(lastRequestParams.current).then((result) => {
            setDisabledNext(false);
            setData(result);
        });
    };

    useEffect(() => {
        getRunsRequest().then((result) => {
            setPagesCount(1);
            setDisabledNext(false);
            setData(result);
        });
    }, [project_name, only_active]);

    const nextPage = async () => {
        if (data.length === 0 || disabledNext) {
            return;
        }

        try {
            const result = await getRunsRequest({
                prev_submitted_at: data[data.length - 1].submitted_at,
                prev_run_id: data[data.length - 1].id,
            });

            if (result.length > 0) {
                setPagesCount((count) => count + 1);
                setData(result);
            } else {
                setDisabledNext(true);
            }
        } catch (e) {
            console.log(e);
        }
    };

    const prevPage = async () => {
        if (pagesCount === 1) {
            return;
        }

        try {
            const result = await getRunsRequest({
                prev_submitted_at: data[0].submitted_at,
                prev_run_id: data[0].id,
                ascending: true,
            });

            setDisabledNext(false);

            if (result.length > 0) {
                setPagesCount((count) => count - 1);
                setData(_orderBy(result, ['submitted_at'], ['desc']));
            } else {
                setPagesCount(1);
            }
        } catch (e) {
            console.log(e);
        }
    };

    return { data, pagesCount, disabledNext, isLoading: isLoading || isFetching, nextPage, prevPage, refreshList };
};
