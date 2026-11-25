import { CollectionPreferencesProps } from 'components';

export const DEFAULT_PREFERENCES: CollectionPreferencesProps.Preferences = {
    pageSize: 30,
    contentDisplay: [
        { id: 'model_name', visible: true },
        { id: 'status', visible: true },
        { id: 'project', visible: true },
        { id: 'run', visible: true },
        { id: 'submitted_at', visible: true },
        { id: 'user', visible: true },
        // hidden by default
        { id: 'resources', visible: false },
        { id: 'price', visible: false },
        { id: 'repository', visible: false },
        { id: 'backend', visible: false },
    ],
    wrapLines: false,
    stripedRows: false,
    contentDensity: 'comfortable',
};
