import { CollectionPreferencesProps } from 'components';

import { useLocalStorageState } from 'hooks/useLocalStorageState';

import { DEFAULT_PREFERENCES } from './consts';

export const useModelListPreferences = () => {
    // A new key: preferences saved under `model-list-preferences` have the list's old columns and would hide Status and Project
    const [preferences, setPreferences] = useLocalStorageState<CollectionPreferencesProps.Preferences>(
        'model-list-preferences-v2',
        DEFAULT_PREFERENCES,
    );

    return [preferences, setPreferences] as const;
};
