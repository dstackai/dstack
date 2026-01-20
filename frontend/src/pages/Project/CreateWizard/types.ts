import { FleetFormFields } from 'pages/Fleets/Add/FleetFormFields/type';

export interface IProjectWizardForm extends Pick<IProject, 'project_name'> {
    project_type: 'gpu_marketplace' | 'own_cloud';
    backends: TBackendType[];
    fleet: FleetFormFields & {
        enable_default?: boolean;
    };
}
