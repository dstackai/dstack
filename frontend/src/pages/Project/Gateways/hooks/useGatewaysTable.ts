import { useNavigate } from 'react-router-dom';

import { ROUTES } from 'routes';
import { useDeleteProjectGatewayMutation, useGetProjectGatewaysQuery } from 'services/gateway';

export const useGatewaysTable = (projectName: IProject['project_name']) => {
    const navigate = useNavigate();
    const { data, isLoading } = useGetProjectGatewaysQuery({ projectName });
    const [deleteGatewayRequest, { isLoading: isDeleting }] = useDeleteProjectGatewayMutation();

    const editGateway = (gateway: IGateway) => {
        navigate(ROUTES.PROJECT.GATEWAY.EDIT.FORMAT(projectName, gateway.name));
    };

    const deleteGateway = (gateways: readonly IGateway[] | IGateway[]) => {
        deleteGatewayRequest({
            projectName,
            names: gateways.map((gateway) => gateway.name),
        });
    };

    const addGateway = () => {
        navigate(ROUTES.PROJECT.GATEWAY.ADD.FORMAT(projectName));
    };

    return { data, isLoading, isDeleting, editGateway, deleteGateway, addGateway } as const;
};
