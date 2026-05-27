export interface IProps {
    gateways: IGateway[];
    projectName: string;
    addItem?: () => void;
    deleteItem?: (gateways: readonly IGateway[] | IGateway[]) => void;
    editItem?: (gateways: IGateway) => void;
    isDisabledDelete?: boolean;
}
