import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { useNotifications } from 'hooks';
import { useDeleteRunsMutation } from 'services/run';

import { getGroupedRunsByProjectAndRepoID } from '../helpers';

export const useDeleteRuns = () => {
    const { t } = useTranslation();
    const [deleteRun, { isLoading: isDeleting }] = useDeleteRunsMutation();
    const [pushNotification] = useNotifications();

    const deleteRuns = useCallback((runs: IRunListItem[]) => {
        const groupedRuns = getGroupedRunsByProjectAndRepoID(runs);

        const request = Promise.all(
            Object.keys(groupedRuns).map((key) => {
                const runsGroup = groupedRuns[key];

                return deleteRun({
                    name: runsGroup[0].project,
                    repo_id: runsGroup[0]?.repo_id ?? undefined,
                    run_names: runsGroup.map((item) => item.run_head.run_name),
                }).unwrap();
            }),
        );

        request.catch((error) => {
            pushNotification({
                type: 'error',
                content: t('common.server_error', { error: error?.error }),
            });
        });

        return request;
    }, []);

    return { deleteRuns, isDeleting } as const;
};
