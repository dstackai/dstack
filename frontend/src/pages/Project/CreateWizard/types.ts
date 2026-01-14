export interface IProjectWizardForm extends Pick<IProject, 'project_name'> {
    project_type: 'gpu_marketplace' | 'own_cloud';
    backends: TBackendType[];
    enable_default_fleet?: boolean;
    fleet_name?: string;
    fleet_min_instances: number;
    fleet_max_instances?: number;
    fleet_idle_duration?: string;
}
