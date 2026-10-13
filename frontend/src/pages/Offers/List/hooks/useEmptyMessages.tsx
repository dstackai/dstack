import React, { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { Button, ListEmptyMessage } from 'components';

import { ROUTES } from 'routes';

export const useEmptyMessages = ({
    clearFilter,
    projectName,
    groupBySelected,
    hasCustomFilters,
}: {
    clearFilter?: () => void;
    projectName?: string;
    groupBySelected?: boolean;
    hasCustomFilters?: boolean;
}) => {
    const { t } = useTranslation();
    const navigate = useNavigate();

    const renderNoMatchMessage = useCallback<() => React.ReactNode>(() => {
        return (
            <ListEmptyMessage title={t('offer.nomatch_message_title')} message={t('offer.nomatch_message_text')}>
                <Button onClick={clearFilter}>{t('common.clearFilter')}</Button>
            </ListEmptyMessage>
        );
    }, [clearFilter]);

    const renderEmptyMessage = useCallback<() => React.ReactNode>(() => {
        if (!projectName) {
            return (
                <ListEmptyMessage
                    title={t('offer.empty_message_title_select_project')}
                    message={t('offer.empty_message_text_select_project')}
                ></ListEmptyMessage>
            );
        }

        if (!groupBySelected) {
            return (
                <ListEmptyMessage
                    title={t('offer.empty_message_title_select_groupBy')}
                    message={t('offer.empty_message_text_select_groupBy')}
                ></ListEmptyMessage>
            );
        }

        if (hasCustomFilters) {
            return renderNoMatchMessage();
        }

        return (
            <ListEmptyMessage title={t('offer.empty_message_title')} message={t('offer.empty_message_text')}>
                <Button onClick={() => navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(projectName))}>
                    {t('common.settings')}
                </Button>
            </ListEmptyMessage>
        );
    }, [projectName, groupBySelected, hasCustomFilters, renderNoMatchMessage]);

    return { renderEmptyMessage, renderNoMatchMessage } as const;
};
