import { FleetFormFields } from 'pages/Fleets/Details/components/FleetFormFields/type';

export interface IProps {
    initialValues?: Partial<IProjectForm>;
    loading?: boolean;
    onCancel: () => void;
    onSubmit: (user: IProject) => Promise<IProject>;
}

export interface IProjectForm extends IProjectCreateRequestParams {
    fleet: FleetFormFields & {
        enable_default?: boolean;
    };
}
