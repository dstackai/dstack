import React from 'react';
import { useTranslation } from 'react-i18next';
import Button from '@cloudscape-design/components/button';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';

import { IProps } from './types';

export const DetailsHeader: React.FC<IProps> = ({
    title,
    actionButtons,
    editAction,
    deleteAction,
    editDisabled,
    deleteDisabled,
}) => {
    const { t } = useTranslation();

    return (
        <Header
            variant="awsui-h1-sticky"
            actions={
                <SpaceBetween direction="horizontal" size="xs">
                    {actionButtons}

                    {editAction && (
                        <Button onClick={editAction} disabled={editDisabled}>
                            {t('common.edit')}
                        </Button>
                    )}

                    {deleteAction && (
                        <Button onClick={deleteAction} disabled={deleteDisabled}>
                            {t('common.delete')}
                        </Button>
                    )}
                </SpaceBetween>
            }
        >
            {title}
        </Header>
    );
};
