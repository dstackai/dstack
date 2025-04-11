import { CollectionPreferencesProps } from 'components';

export const DEFAULT_PREFERENCES: CollectionPreferencesProps.Preferences = {
    pageSize: 30,
    contentDisplay: [
        { id: 'run_name', visible: true },
        { id: 'resources', visible: true },
        { id: 'spot', visible: true },
        { id: 'price', visible: true },
        { id: 'submitted_at', visible: true },
        { id: 'status', visible: true },
        { id: 'error', visible: true },
        { id: 'cost', visible: true },
        // hidden by default
        { id: 'finished_at', visible: false },
        { id: 'project', visible: false },
        { id: 'hub_user_name', visible: false },
        { id: 'repo', visible: false },
        { id: 'instance', visible: false },
        { id: 'region', visible: false },
        { id: 'backend', visible: false },
    ],
    wrapLines: false,
    stripedRows: false,
    contentDensity: 'comfortable',
};
