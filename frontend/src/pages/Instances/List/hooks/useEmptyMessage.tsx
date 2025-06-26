import React, { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { Button, ListEmptyMessage } from 'components';

export const useEmptyMessages = ({
    clearFilter,
    isDisabledClearFilter,
}: {
    clearFilter?: () => void;
    isDisabledClearFilter?: boolean;
}) => {
    const { t } = useTranslation();

    const renderEmptyMessage = useCallback<() => React.ReactNode>(() => {
        return (
            <ListEmptyMessage
                title={t('fleets.instances.empty_message_title')}
                message={t('fleets.instances.empty_message_text')}
            >
                <Button disabled={isDisabledClearFilter} onClick={clearFilter}>
                    {t('common.clearFilter')}
                </Button>
            </ListEmptyMessage>
        );
    }, [clearFilter, isDisabledClearFilter]);

    const renderNoMatchMessage = useCallback<() => React.ReactNode>(() => {
        return (
            <ListEmptyMessage
                title={t('fleets.instances.nomatch_message_title')}
                message={t('fleets.instances.nomatch_message_text')}
            >
                <Button disabled={isDisabledClearFilter} onClick={clearFilter}>
                    {t('common.clearFilter')}
                </Button>
            </ListEmptyMessage>
        );
    }, [clearFilter, isDisabledClearFilter]);

    return { renderEmptyMessage, renderNoMatchMessage } as const;
};
