import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { useNotifications } from 'hooks';
import { getServerError } from 'libs';
import { ROUTES } from 'routes';
import { useDeleteProjectBackendMutation } from 'services/backend';

export const useBackendsTable = (projectName: IProject['project_name'], backends: IProject['backends']) => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const [deleteBackendRequest, { isLoading: isDeleting }] = useDeleteProjectBackendMutation();
    const [pushNotification] = useNotifications();

    const editBackend = (backend: IProjectBackend) => {
        navigate(ROUTES.PROJECT.BACKEND.EDIT.FORMAT(projectName, backend.name));
    };

    const deleteBackend = (backends: readonly IProjectBackend[] | IProjectBackend[]) => {
        deleteBackendRequest({
            projectName,
            backends_names: backends.map((backend) => backend.name),
        })
            .unwrap()
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: getServerError(error) }),
                });
            });
    };

    const addBackend = () => {
        navigate(ROUTES.PROJECT.BACKEND.ADD.FORMAT(projectName));
    };

    return { data: backends, isDeleting, editBackend, deleteBackend, addBackend } as const;
};
