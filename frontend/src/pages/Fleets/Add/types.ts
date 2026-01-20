import { FleetFormFields } from './FleetFormFields/type';

export interface IFleetWizardForm extends FleetFormFields {
    project_name: IProject['project_name'];
}
