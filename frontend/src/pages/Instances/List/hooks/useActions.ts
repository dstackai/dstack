import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useNotifications } from 'hooks';
import { getServerError } from 'libs';
import { useDeleteInstancesMutation } from 'services/instance';

export const useActions = () => {
    const { t } = useTranslation();
    const [deleteInstances] = useDeleteInstancesMutation();
    const [pushNotification] = useNotifications();
    const [isDeleting, setIsDeleting] = useState(() => false);

    const instancesGroupByFleetName = (instances: IInstance[]) => {
        return instances.reduce<Record<string, number[]>>((acc, instance) => {
            const key = `${instance.project_name}/${instance.fleet_name}`;

            if (acc[key]) {
                acc[key].push(instance.instance_num);
            } else {
                acc[key] = [instance.instance_num];
            }

            return acc;
        }, {});
    };

    const deleteFleets = useCallback(async (instances: IInstance[]) => {
        if (!instances.length) return Promise.reject('No instances');

        setIsDeleting(true);

        const groupedInstances = instancesGroupByFleetName(instances);

        const requests = Object.keys(groupedInstances).map((key) => {
            const [projectName, fleetName] = key.split('/');

            return deleteInstances({
                projectName,
                fleetName,
                instancesNums: groupedInstances[key],
            }).unwrap();
        });

        return Promise.all(requests)
            .finally(() => setIsDeleting(false))
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: getServerError(error) }),
                });
            });
    }, []);

    return { deleteFleets, isDeleting } as const;
};
