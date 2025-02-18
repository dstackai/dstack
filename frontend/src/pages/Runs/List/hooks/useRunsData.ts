import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useInfiniteScroll } from 'hooks';
import { useLazyGetRunsQuery } from 'services/run';

export const useRunsData = ({ project_name, only_active }: TRunsRequestParams) => {
    const { data, isLoading, refreshList } = useInfiniteScroll<IRun, TRunsRequestParams>({
        useLazyQuery: useLazyGetRunsQuery,
        args: { project_name, only_active, limit: DEFAULT_TABLE_PAGE_SIZE },
    });

    return { data, isLoading, refreshList };
};
