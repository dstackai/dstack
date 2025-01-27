import { useEffect, useRef, useState } from 'react';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useLazyGetInstancesQuery } from 'services/instance';

export const useInstanceListData = ({ project_names, only_active, fleet_ids }: TInstanceListRequestParams) => {
    const [data, setData] = useState<IInstance[]>([]);
    const [pagesCount, setPagesCount] = useState<number>(1);
    const [disabledNext, setDisabledNext] = useState(false);
    const lastRequestParams = useRef<TInstanceListRequestParams | undefined>(undefined);

    const [getInstances, { isLoading, isFetching }] = useLazyGetInstancesQuery();

    const getInstancesRequest = (params?: TInstanceListRequestParams) => {
        lastRequestParams.current = params;

        return getInstances({
            project_names,
            fleet_ids,
            only_active,
            limit: DEFAULT_TABLE_PAGE_SIZE,
            ...params,
        }).unwrap();
    };

    const refreshList = () => {
        getInstancesRequest(lastRequestParams.current).then((result) => {
            setDisabledNext(false);
            setData(result);
        });
    };

    useEffect(() => {
        getInstancesRequest().then((result) => {
            setPagesCount(1);
            setDisabledNext(false);
            setData(result);
        });
    }, [project_names, only_active, fleet_ids]);

    const nextPage = async () => {
        if (data.length === 0 || disabledNext) {
            return;
        }

        try {
            const result = await getInstancesRequest({
                prev_created_at: data[data.length - 1].created,
                prev_id: data[data.length - 1].id,
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
            const result = await getInstancesRequest({
                prev_created_at: data[0].created,
                prev_id: data[0].id,
                ascending: true,
            });

            setDisabledNext(false);

            if (result.length > 0) {
                setPagesCount((count) => count - 1);
                setData(result);
            } else {
                setPagesCount(1);
            }
        } catch (e) {
            console.log(e);
        }
    };

    return { data, pagesCount, disabledNext, isLoading: isLoading || isFetching, nextPage, prevPage, refreshList };
};
