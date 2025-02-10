import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useNotifications } from 'hooks';
import { getServerError } from 'libs';
import { useDeleteFleetMutation } from 'services/fleet';

export const useDeleteFleet = () => {
    const { t } = useTranslation();
    const [deleteFleet] = useDeleteFleetMutation();
    const [pushNotification] = useNotifications();
    const [isDeleting, setIsDeleting] = useState(() => false);

    const namesOfFleetsGroupByProjectName = (volumes: IFleet[]) => {
        return volumes.reduce<Record<string, string[]>>((acc, fleet) => {
            if (acc[fleet.project_name]) {
                acc[fleet.project_name].push(fleet.name);
            } else {
                acc[fleet.project_name] = [fleet.name];
            }

            return acc;
        }, {});
    };

    const deleteFleets = useCallback(async (fleets: IFleet[]) => {
        if (!fleets.length) return Promise.reject('No fleets');

        setIsDeleting(true);

        const groupedFleets = namesOfFleetsGroupByProjectName(fleets);

        const requests = Object.keys(groupedFleets).map((projectName) => {
            return deleteFleet({
                projectName: projectName,
                fleetNames: groupedFleets[projectName],
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
