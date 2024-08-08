import { useNavigate } from 'react-router-dom';

import { ROUTES } from 'routes';
import { useDeleteProjectBackendMutation } from 'services/backend';

export const useBackendsTable = (projectName: IProject['project_name'], backends: IProject['backends']) => {
    const navigate = useNavigate();
    const [deleteBackendRequest, { isLoading: isDeleting }] = useDeleteProjectBackendMutation();

    const editBackend = (backend: IProjectBackend) => {
        navigate(ROUTES.PROJECT.BACKEND.EDIT.FORMAT(projectName, backend.name));
    };

    const deleteBackend = (backends: readonly IProjectBackend[] | IProjectBackend[]) => {
        deleteBackendRequest({
            projectName,
            backends_names: backends.map((backend) => backend.name),
        });
    };

    const addBackend = () => {
        navigate(ROUTES.PROJECT.BACKEND.ADD.FORMAT(projectName));
    };

    return { data: backends, isDeleting, editBackend, deleteBackend, addBackend } as const;
};
