import { useNavigate } from 'react-router-dom';

import { ROUTES } from 'routes';
import { useDeleteProjectBackendMutation, useGetProjectBackendsQuery } from 'services/backend';

export const useBackendsTable = (projectName: IProject['project_name']) => {
    const navigate = useNavigate();
    const { data, isLoading } = useGetProjectBackendsQuery({ projectName });
    const [deleteBackendRequest, { isLoading: isDeleting }] = useDeleteProjectBackendMutation();

    const editBackend = (backend: IProjectBackend) => {
        navigate(ROUTES.PROJECT.BACKEND.EDIT.FORMAT(projectName, backend.name));
    };

    const deleteBackend = (backends: readonly IProjectBackend[] | IProjectBackend[]) => {
        deleteBackendRequest({
            projectName,
            backends: backends.map((backend) => backend.name),
        });
    };

    const addBackend = () => {
        navigate(ROUTES.PROJECT.BACKEND.ADD.FORMAT(projectName));
    };

    return { data, isLoading, isDeleting, editBackend, deleteBackend, addBackend } as const;
};
