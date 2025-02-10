import { useTranslation } from 'react-i18next';

import { useNotifications } from 'hooks';
import { getServerError } from 'libs';
import { useDeleteProjectsMutation } from 'services/project';

export const useDeleteProject = () => {
    const { t } = useTranslation();
    const [deleteProjectsRequest, { isLoading: isDeleting }] = useDeleteProjectsMutation();
    const [pushNotification] = useNotifications();

    const deleteProject = (project: IProject) => {
        const request = deleteProjectsRequest([project.project_name]).unwrap();

        request.catch((error) => {
            pushNotification({
                type: 'error',
                content: t('common.server_error', { error: getServerError(error) }),
            });
        });

        return request;
    };

    const deleteProjects = (projects: IProject[]) => {
        const request = deleteProjectsRequest(projects.map((project) => project.project_name)).unwrap();

        request.catch((error) => {
            pushNotification({
                type: 'error',
                content: t('common.server_error', { error: getServerError(error) }),
            });
        });

        return request;
    };

    return { isDeleting, deleteProject, deleteProjects } as const;
};
