import React, { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { Button, ListEmptyMessage } from 'components';

import { QUICK_START_URL } from 'consts';
import { goToUrl } from 'libs';

export const useEmptyMessages = ({
    clearFilter,
    noData,
    isDisabledClearFilter,
}: {
    clearFilter?: () => void;
    noData?: boolean;
    isDisabledClearFilter?: boolean;
}) => {
    const { t } = useTranslation();

    const renderEmptyMessage = useCallback<() => React.ReactNode>(() => {
        if (noData && isDisabledClearFilter) {
            return (
                <ListEmptyMessage
                    title={t('projects.run.empty_message_title')}
                    message={t('projects.run.quickstart_message_text')}
                >
                    <Button variant="primary" external onClick={() => goToUrl(QUICK_START_URL, true)}>
                        {t('common.quickstart')}
                    </Button>
                </ListEmptyMessage>
            );
        }

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
