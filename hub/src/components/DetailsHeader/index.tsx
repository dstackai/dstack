import React from 'react';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Button from '@cloudscape-design/components/button';
import { IProps } from './types';
import { useTranslation } from 'react-i18next';

export const DetailsHeader: React.FC<IProps> = ({ title, editAction, deleteAction, editDisabled, deleteDisabled }) => {
    const { t } = useTranslation();

    return (
        <Header
            variant="awsui-h1-sticky"
            actions={
                <SpaceBetween direction="horizontal" size="xs">
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
