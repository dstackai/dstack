import React from 'react';
import { useTranslation } from 'react-i18next';

import { CollectionPreferences } from 'components';

import { useRunListPreferences } from './useRunListPreferences';

export const Preferences: React.FC = () => {
    const { t } = useTranslation();
    const [preferences, setPreferences] = useRunListPreferences();

    return (
        <CollectionPreferences
            preferences={preferences}
            onConfirm={({ detail }) => setPreferences(detail)}
            cancelLabel={t('common.cancel')}
            confirmLabel={t('common.save')}
            contentDisplayPreference={{
                title: t('common.select_visible_columns'),
                options: [
                    { id: 'run_name', label: t('projects.run.run_name'), alwaysVisible: true },
                    { id: 'resources', label: t('projects.run.resources') },
                    { id: 'spot', label: t('projects.run.spot') },
                    { id: 'price', label: t('projects.run.price') },
                    { id: 'submitted_at', label: t('projects.run.submitted_at') },
                    { id: 'status', label: t('projects.run.status') },
                    { id: 'error', label: t('projects.run.error') },
                    { id: 'cost', label: t('projects.run.cost') },
                    // hidden by default
                    { id: 'priority', label: t('projects.run.priority') },
                    { id: 'finished_at', label: t('projects.run.finished_at') },
                    { id: 'project', label: t('projects.run.project') },
                    { id: 'hub_user_name', label: t('projects.run.hub_user_name') },
                    { id: 'repo', label: t('projects.run.repo') },
                    { id: 'instance', label: t('projects.run.instance') },
                    { id: 'region', label: t('projects.run.region') },
                    { id: 'backend', label: t('projects.run.backend') },
                ],
            }}
        />
    );
};
