import React, { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { Button, ListEmptyMessage } from 'components';

export const useEmptyMessages = ({
    clearFilter,
    isDisabledClearFilter,
    projectNameSelected,
    groupBySelected,
}: {
    clearFilter?: () => void;
    isDisabledClearFilter?: boolean;
    projectNameSelected?: boolean;
    groupBySelected?: boolean;
}) => {
    const { t } = useTranslation();

    const renderEmptyMessage = useCallback<() => React.ReactNode>(() => {
        if (!projectNameSelected) {
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

        return (
            <ListEmptyMessage title={t('offer.empty_message_title')} message={t('offer.empty_message_text')}>
                <Button disabled={isDisabledClearFilter} onClick={clearFilter}>
                    {t('common.clearFilter')}
                </Button>
            </ListEmptyMessage>
        );
    }, [clearFilter, isDisabledClearFilter]);

    const renderNoMatchMessage = useCallback<() => React.ReactNode>(() => {
        return (
            <ListEmptyMessage title={t('offer.nomatch_message_title')} message={t('offer.nomatch_message_text')}>
                <Button disabled={isDisabledClearFilter} onClick={clearFilter}>
                    {t('common.clearFilter')}
                </Button>
            </ListEmptyMessage>
        );
    }, [clearFilter, isDisabledClearFilter]);

    return { renderEmptyMessage, renderNoMatchMessage } as const;
};
