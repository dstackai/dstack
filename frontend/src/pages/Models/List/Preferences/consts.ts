import { CollectionPreferencesProps } from 'components';

export const DEFAULT_PREFERENCES: CollectionPreferencesProps.Preferences = {
    pageSize: 30,
    contentDisplay: [
        { id: 'model_name', visible: true },
        { id: 'type', visible: true },
        { id: 'run', visible: true },
        { id: 'resources', visible: true },
        { id: 'price', visible: true },
        { id: 'submitted_at', visible: true },
        { id: 'user', visible: true },
        { id: 'repository', visible: true },
        { id: 'backend', visible: true },
        // hidden by default
        { id: 'url', visible: false },
    ],
    wrapLines: false,
    stripedRows: false,
    contentDensity: 'comfortable',
};
