import { useNavigate } from 'react-router-dom';

import { ROUTES } from 'routes';
import { useGetProjectGatewaysQuery } from 'services/gateway';

export const useGatewaysTable = (projectName: IProject['project_name']) => {
    const navigate = useNavigate();
    const { data, isLoading } = useGetProjectGatewaysQuery({ projectName });
    const isDeleting = false;
    // const [deleteBackendRequest, { isLoading: isDeleting }] = useDeleteProjectBackendMutation();

    const editGateway = (gateway: IGateway) => {
        console.log(gateway);
        // navigate(ROUTES.PROJECT.BACKEND.EDIT.FORMAT(projectName, gateway.head.instance_name));
    };

    const deleteGateway = (gateways: readonly IGateway[] | IGateway[]) => {
        console.log(gateways);
        // deleteBackendRequest({
        //     projectName,
        //     backends: backends.map((backend) => backend.name),
        // });
    };

    const addGateway = () => {
        navigate(ROUTES.PROJECT.GATEWAY.ADD.FORMAT(projectName));
    };

    return { data, isLoading, isDeleting, editGateway, deleteGateway, addGateway } as const;
};
