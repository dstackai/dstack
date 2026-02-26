import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useNotifications } from 'hooks';
import { getServerError } from 'libs';
import { useDeleteInstancesMutation } from 'services/instance';

export const useDeleteInstance = () => {
    const { t } = useTranslation();
    const [deleteInstances] = useDeleteInstancesMutation();
    const [pushNotification] = useNotifications();
    const [isDeleting, setIsDeleting] = useState(false);

    const deleteInstance = useCallback(async (instance: IInstance) => {
        if (!instance.project_name || !instance.fleet_name) {
            return Promise.reject('Missing project or fleet name');
        }

        setIsDeleting(true);

        return deleteInstances({
            projectName: instance.project_name,
            fleetName: instance.fleet_name,
            instancesNums: [instance.instance_num],
        })
            .unwrap()
            .finally(() => setIsDeleting(false))
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: getServerError(error) }),
                });
                throw error;
            });
    }, []);

    return { deleteInstance, isDeleting } as const;
};
