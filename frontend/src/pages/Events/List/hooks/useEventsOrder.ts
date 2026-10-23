import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import type { TableProps } from 'components';

const ORDER_SEARCH_PARAM_KEY = 'order';

export const useEventsOrder = ({ withSearchParams }: { withSearchParams?: boolean } = {}) => {
    const [searchParams, setSearchParams] = useSearchParams();

    const [ascending, setAscending] = useState<boolean>(
        () => !!withSearchParams && searchParams.get(ORDER_SEARCH_PARAM_KEY) === 'asc',
    );

    const onSortingChange: TableProps['onSortingChange'] = ({ detail }) => {
        setAscending(!detail.isDescending);

        if (!withSearchParams) {
            return;
        }

        setSearchParams((prevSearchParams) => {
            const nextSearchParams = new URLSearchParams(prevSearchParams);

            if (detail.isDescending) {
                nextSearchParams.delete(ORDER_SEARCH_PARAM_KEY);
            } else {
                nextSearchParams.set(ORDER_SEARCH_PARAM_KEY, 'asc');
            }

            return nextSearchParams;
        });
    };

    // Events are sorted on the server, so the table only displays and changes the order
    const sortingProps: Pick<TableProps<IEvent>, 'sortingColumn' | 'sortingDescending' | 'onSortingChange'> = {
        sortingColumn: { sortingField: 'recorded_at' },
        sortingDescending: !ascending,
        onSortingChange,
    };

    return { ascending, sortingProps } as const;
};
