import React from 'react';
import { useTranslation } from 'react-i18next';

import { Button, ButtonWithConfirmation, Header, ListEmptyMessage, SpaceBetween, Table } from 'components';

import { useCollection } from 'hooks';

import { useColumnsDefinitions } from './hooks';

import { IProps } from './types';

export const GatewaysTable: React.FC<IProps> = ({ gateways, addItem, deleteItem, editItem, isDisabledDelete }) => {
    const { t } = useTranslation();

    const renderEmptyMessage = (): React.ReactNode => {
        return (
            <ListEmptyMessage title={t('gateway.empty_message_title')} message={t('gateway.empty_message_text')}>
                {addItem && <Button onClick={addItem}>{t('common.add')}</Button>}
            </ListEmptyMessage>
        );
    };

    const { items, collectionProps } = useCollection(gateways ?? [], {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderEmptyMessage(),
        },
        selection: {},
    });

    const { selectedItems } = collectionProps;

    const isDisabledDeleteSelected = !selectedItems?.length || isDisabledDelete;

    const deleteSelectedGateways = () => {
        if (!selectedItems?.length || !deleteItem) return;

        deleteItem(selectedItems);
    };

    const { columns } = useColumnsDefinitions({
        ...(editItem ? { onEditClick: (gateway) => editItem(gateway) } : {}),
        ...(deleteItem ? { onDeleteClick: (gateway) => deleteItem([gateway]) } : {}),
    });

    const renderCounter = () => {
        if (!gateways?.length) return '';

        return `(${gateways.length})`;
    };

    return (
        <Table
            {...collectionProps}
            columnDefinitions={columns}
            items={items}
            loadingText={t('common.loading')}
            selectionType="multi"
            stickyHeader={true}
            header={
                <Header
                    counter={renderCounter()}
                    actions={
                        <SpaceBetween size="xs" direction="horizontal">
                            {deleteItem && (
                                <ButtonWithConfirmation
                                    disabled={isDisabledDeleteSelected}
                                    formAction="none"
                                    onClick={deleteSelectedGateways}
                                    confirmTitle={t('gateway.edit.delete_gateways_confirm_title')}
                                    confirmContent={t('gateway.edit.delete_gateways_confirm_message')}
                                >
                                    {t('common.delete')}
                                </ButtonWithConfirmation>
                            )}

                            {addItem && <Button onClick={addItem}>{t('common.add')}</Button>}
                        </SpaceBetween>
                    }
                >
                    {t('gateway.page_title_other')}
                </Header>
            }
        />
    );
};
