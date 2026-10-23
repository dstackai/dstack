import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import type { TableProps } from 'components';

const ORDER_SEARCH_PARAM_KEY = 'order';

// Search params that open the global Events page in the specified order
export const getEventsOrderSearchParams = (ascending: boolean): Record<string, string> =>
    ascending ? { [ORDER_SEARCH_PARAM_KEY]: 'asc' } : {};

export const useEventsOrder = ({ withSearchParams }: { withSearchParams?: boolean } = {}) => {
    const [searchParams, setSearchParams] = useSearchParams();
    const [localAscending, setLocalAscending] = useState<boolean>(false);

    // Read from search params on every render to stay in sync with browser navigation
    const ascending = withSearchParams ? searchParams.get(ORDER_SEARCH_PARAM_KEY) === 'asc' : localAscending;

    const onSortingChange: TableProps['onSortingChange'] = ({ detail }) => {
        if (!withSearchParams) {
            setLocalAscending(!detail.isDescending);
            return;
        }

        setSearchParams(
            (prevSearchParams) => {
                const nextSearchParams = new URLSearchParams(prevSearchParams);

                if (detail.isDescending) {
                    nextSearchParams.delete(ORDER_SEARCH_PARAM_KEY);
                } else {
                    nextSearchParams.set(ORDER_SEARCH_PARAM_KEY, 'asc');
                }

                return nextSearchParams;
            },
            { replace: true },
        );
    };

    // Events are sorted on the server, so the table only displays and changes the order
    const sortingProps: Pick<TableProps<IEvent>, 'sortingColumn' | 'sortingDescending' | 'onSortingChange'> = {
        sortingColumn: { sortingField: 'recorded_at' },
        sortingDescending: !ascending,
        onSortingChange,
    };

    return { ascending, sortingProps } as const;
};
