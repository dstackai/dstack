import { CollectionPreferencesProps } from 'components';

export const DEFAULT_PREFERENCES: CollectionPreferencesProps.Preferences = {
    pageSize: 30,
    contentDisplay: [
        { id: 'run_name', visible: true },
        { id: 'resources', visible: true },
        { id: 'status', visible: true },
        { id: 'hub_user_name', visible: true },
        { id: 'submitted_at', visible: true },
        { id: 'finished_at', visible: true },
        { id: 'error', visible: true },
        { id: 'price', visible: true },
        { id: 'cost', visible: true },
        { id: 'spot', visible: true },
        { id: 'backend', visible: true },
        { id: 'region', visible: true },
        // hidden by default
        { id: 'priority', visible: false },
        { id: 'project', visible: false },
        { id: 'repo', visible: false },
        { id: 'instance', visible: false },
    ],
    wrapLines: false,
    stripedRows: false,
    contentDensity: 'comfortable',
};
