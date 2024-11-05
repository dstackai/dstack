import React from 'react';
import { useTranslation } from 'react-i18next';

import { CollectionPreferences } from 'components';

import { useModelListPreferences } from './useModelListPreferences';

export const Preferences: React.FC = () => {
    const { t } = useTranslation();
    const [preferences, setPreferences] = useModelListPreferences();

    return (
        <CollectionPreferences
            preferences={preferences}
            onConfirm={({ detail }) => setPreferences(detail)}
            cancelLabel={t('common.cancel')}
            confirmLabel={t('common.save')}
            contentDisplayPreference={{
                title: t('common.select_visible_columns'),
                options: [
                    { id: 'model_name', label: t('models.model_name'), alwaysVisible: true },
                    { id: 'type', label: `${t('models.type')}` },

                    { id: 'run', label: `${t('models.run')}` },
                    { id: 'resources', label: `${t('models.resources')}` },
                    { id: 'price', label: `${t('models.price')}` },
                    { id: 'submitted_at', label: `${t('models.submitted_at')}` },
                    { id: 'user', label: `${t('models.user')}` },
                    { id: 'repository', label: `${t('models.repository')}` },
                    { id: 'backend', label: `${t('models.backend')}` },
                    // hidden by default
                    { id: 'url', label: `${t('models.url')}` },
                ],
            }}
        />
    );
};
