import { CollectionPreferencesProps } from 'components';

import { useLocalStorageState } from 'hooks/useLocalStorageState';

import { DEFAULT_PREFERENCES } from './consts';

export const useModelListPreferences = () => {
    const [preferences, setPreferences] = useLocalStorageState<CollectionPreferencesProps.Preferences>(
        'model-list-preferences',
        DEFAULT_PREFERENCES,
    );

    return [preferences, setPreferences] as const;
};
