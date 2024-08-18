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
            <ListEmptyMessage title={t('projects.run.nomatch_message_title')} message={t('projects.run.nomatch_message_text')}>
                <Button disabled={isDisabledClearFilter} onClick={clearFilter}>
                    {t('common.clearFilter')}
                </Button>
            </ListEmptyMessage>
        );
    }, [isDisabledClearFilter, clearFilter]);

    const renderNoMatchMessage = useCallback<() => React.ReactNode>(() => {
        return (
            <ListEmptyMessage title={t('projects.run.nomatch_message_title')} message={t('projects.run.nomatch_message_text')}>
                <Button disabled={isDisabledClearFilter} onClick={clearFilter}>
                    {t('common.clearFilter')}
                </Button>
            </ListEmptyMessage>
        );
    }, [isDisabledClearFilter, clearFilter]);

    return { renderEmptyMessage, renderNoMatchMessage } as const;
};
