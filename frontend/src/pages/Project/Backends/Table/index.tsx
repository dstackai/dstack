import React from 'react';
import { useTranslation } from 'react-i18next';

import { Button, ButtonWithConfirmation, Header, InfoLink, ListEmptyMessage, SpaceBetween, Table } from 'components';

import { useCollection, useHelpPanel } from 'hooks';

import { BACKENDS_HELP_ENTERPRISE, BACKENDS_HELP_SKY } from './constants';
import { useColumnsDefinitions } from './hooks';

import { IProps } from './types';
const INFO = process.env.UI_VERSION === 'enterprise' ? BACKENDS_HELP_ENTERPRISE : BACKENDS_HELP_SKY;

export const BackendsTable: React.FC<IProps> = ({
    backends,
    editBackend,
    deleteBackends,
    onClickAddBackend,
    isDisabledDelete,
}) => {
    const { t } = useTranslation();
    const [openHelpPanel] = useHelpPanel();

    const renderEmptyMessage = (): React.ReactNode => {
        return (
            <ListEmptyMessage title={t('backend.empty_message_title')} message={t('backend.empty_message_text')}>
                {onClickAddBackend && <Button onClick={onClickAddBackend}>{t('common.add')}</Button>}
            </ListEmptyMessage>
        );
    };

    const { items, collectionProps } = useCollection(backends ?? [], {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderEmptyMessage(),
        },
        selection: {},
    });

    const { selectedItems } = collectionProps;

    const isDisabledDeleteSelected = !selectedItems?.length || isDisabledDelete;

    const deleteSelectedBackends = () => {
        if (!selectedItems?.length || !deleteBackends) return;

        deleteBackends(selectedItems);
    };

    const { columns } = useColumnsDefinitions({
        ...(editBackend ? { onEditClick: (backend) => editBackend(backend) } : {}),
    });

    const renderCounter = () => {
        if (!backends?.length) return '';

        return `(${backends.length})`;
    };

    return (
        <Table
            {...collectionProps}
            columnDefinitions={columns}
            items={items}
            loadingText={t('common.loading')}
            selectionType={deleteBackends || editBackend ? 'multi' : undefined}
            stickyHeader={true}
            header={
                <Header
                    counter={renderCounter()}
                    info={<InfoLink onFollow={() => openHelpPanel(INFO)} />}
                    actions={
                        <SpaceBetween size="xs" direction="horizontal">
                            {deleteBackends && (
                                <ButtonWithConfirmation
                                    disabled={isDisabledDeleteSelected}
                                    formAction="none"
                                    onClick={deleteSelectedBackends}
                                    confirmTitle={t('backend.edit.delete_backends_confirm_title')}
                                    confirmContent={t('backend.edit.delete_backends_confirm_message')}
                                >
                                    {t('common.delete')}
                                </ButtonWithConfirmation>
                            )}

                            {onClickAddBackend && (
                                <Button onClick={onClickAddBackend} /*disabled={isDisabledAddBackendButton}*/>
                                    {t('common.add')}
                                </Button>
                            )}
                        </SpaceBetween>
                    }
                >
                    {t('backend.page_title_other')}
                </Header>
            }
        />
    );
};
