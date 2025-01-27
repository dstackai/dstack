import React, { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { Button, ListEmptyMessage } from 'components';

export const useEmptyMessages = ({
    clearFilters,
    isDisabledClearFilter,
}: {
    clearFilters?: () => void;
    isDisabledClearFilter?: boolean;
}) => {
    const { t } = useTranslation();

    const renderEmptyMessage = useCallback<() => React.ReactNode>(() => {
        return (
            <ListEmptyMessage
                title={t('fleets.instances.empty_message_title')}
                message={t('fleets.instances.empty_message_text')}
            >
                <Button disabled={isDisabledClearFilter} onClick={clearFilters}>
                    {t('common.clearFilter')}
                </Button>
            </ListEmptyMessage>
        );
    }, [clearFilters, isDisabledClearFilter]);

    const renderNoMatchMessage = useCallback<() => React.ReactNode>(() => {
        return (
            <ListEmptyMessage
                title={t('fleets.instances.nomatch_message_title')}
                message={t('fleets.instances.nomatch_message_text')}
            >
                <Button disabled={isDisabledClearFilter} onClick={clearFilters}>
                    {t('common.clearFilter')}
                </Button>
            </ListEmptyMessage>
        );
    }, [clearFilters, isDisabledClearFilter]);

    return { renderEmptyMessage, renderNoMatchMessage } as const;
};
