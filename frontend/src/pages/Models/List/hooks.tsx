import React, { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { format } from 'date-fns';

import { ListEmptyMessage, NavigateLink, TableProps } from 'components';

import { DATE_TIME_FORMAT } from 'consts';

import { ROUTES } from '../../../routes';

import { IModelExtended } from './types';

export const useColumnsDefinitions = () => {
    const { t } = useTranslation();

    const columns: TableProps.ColumnDefinition<IModelExtended>[] = [
        {
            id: 'model_name',
            header: t('models.model_name'),
            cell: (item) => {
                return (
                    <NavigateLink href={ROUTES.MODELS.DETAILS.FORMAT(item.project_name, item.run_name)}>
                        {item.name}
                    </NavigateLink>
                );
            },
        },
        {
            id: 'type',
            header: `${t('models.type')}`,
            cell: (item) => item.type,
        },
        {
            id: 'gateway',
            header: `${t('models.gateway')}`,
            cell: (item) => item.base_url,
        },
        {
            id: 'run',
            header: `${t('models.run')}`,
            cell: (item) => (
                <NavigateLink
                    href={ROUTES.PROJECT.DETAILS.RUNS.DETAILS.FORMAT(item.project_name, item.run_name ?? 'No run name')}
                >
                    {item.run_name}
                </NavigateLink>
            ),
        },
        {
            id: 'resources',
            header: `${t('models.resources')}`,
            cell: (item) => item.resources,
        },
        {
            id: 'price',
            header: `${t('models.price')}`,
            cell: (item) => (item.price ? `$${item.price}` : null),
        },
        {
            id: 'submitted_at',
            header: `${t('models.submitted_at')}`,
            cell: (item) => format(new Date(item.submitted_at), DATE_TIME_FORMAT),
        },
        {
            id: 'user',
            header: `${t('models.user')}`,
            cell: (item) => item.user,
        },
        {
            id: 'repository',
            header: `${t('models.repository')}`,
            cell: (item) => item.repository,
        },
        {
            id: 'backend',
            header: `${t('models.backend')}`,
            cell: (item) => item.backend,
        },
    ];

    return { columns } as const;
};

export const useEmptyMessages = () => {
    const { t } = useTranslation();

    const renderEmptyMessage = useCallback<() => React.ReactNode>(() => {
        return <ListEmptyMessage title={t('models.empty_message_title')} message={t('models.empty_message_text')} />;
    }, []);

    const renderNoMatchMessage = useCallback<() => React.ReactNode>(() => {
        return <ListEmptyMessage title={t('models.nomatch_message_title')} message={t('models.nomatch_message_text')} />;
    }, []);

    return { renderEmptyMessage, renderNoMatchMessage } as const;
};
