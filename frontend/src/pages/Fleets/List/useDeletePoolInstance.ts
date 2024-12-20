import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { useNotifications } from 'hooks';
import { useDeletePoolInstanceMutation } from 'services/pool';

export const useDeletePoolInstances = () => {
    const { t } = useTranslation();
    const [deleteInstance, { isLoading: isDeleting }] = useDeletePoolInstanceMutation();
    const [pushNotification] = useNotifications();

    const deleteInstances = useCallback((instances: IInstanceListItem[]) => {
        const request = Promise.all(
            instances.map((instance) => {
                if (!instance.project_name) return Promise.resolve();

                return deleteInstance({
                    projectName: instance.project_name,
                    pool_name: instance.pool_name,
                    instance_name: instance.name,
                    force: true,
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

    return { deleteInstances: deleteInstances, isDeleting } as const;
};
