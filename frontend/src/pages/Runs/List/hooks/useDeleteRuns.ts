import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { useNotifications } from 'hooks';
import { getServerError } from 'libs';
import { useDeleteRunsMutation } from 'services/run';

import { getGroupedRunsByProjectAndRepoID } from '../helpers';

export const useDeleteRuns = () => {
    const { t } = useTranslation();
    const [deleteRun, { isLoading: isDeleting }] = useDeleteRunsMutation();
    const [pushNotification] = useNotifications();

    const deleteRuns = useCallback((runs: IRun[]) => {
        const groupedRuns = getGroupedRunsByProjectAndRepoID(runs);

        const request = Promise.all(
            Object.keys(groupedRuns).map((key) => {
                const runsGroup = groupedRuns[key];

                return deleteRun({
                    project_name: runsGroup[0].project_name,
                    runs_names: runsGroup.map((item) => item.run_spec.run_name),
                }).unwrap();
            }),
        );

        request.catch((error) => {
            pushNotification({
                type: 'error',
                content: t('common.server_error', { error: getServerError(error) }),
            });
        });

        return request;
    }, []);

    return { deleteRuns, isDeleting } as const;
};
