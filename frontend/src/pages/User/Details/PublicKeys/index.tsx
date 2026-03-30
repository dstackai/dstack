import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import CloudscapeInput from '@cloudscape-design/components/input';
import CloudscapeTextarea from '@cloudscape-design/components/textarea';

import { Box, Button, ButtonWithConfirmation, FormField, Header, Modal, SpaceBetween, Table } from 'components';

import { useBreadcrumbs, useCollection, useNotifications } from 'hooks';
import { getServerError } from 'libs';
import { ROUTES } from 'routes';
import { IPublicKey, useAddPublicKeyMutation, useDeletePublicKeysMutation, useListPublicKeysQuery } from 'services/publicKeys';

export const PublicKeys: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramUserName = params.userName ?? '';
    const [pushNotification] = useNotifications();

    const [showAddModal, setShowAddModal] = useState(false);
    const [keyValue, setKeyValue] = useState('');
    const [keyName, setKeyName] = useState('');
    const [addError, setAddError] = useState('');

    const { data: publicKeys = [], isLoading } = useListPublicKeysQuery();
    const [addPublicKey, { isLoading: isAdding }] = useAddPublicKeyMutation();
    const [deletePublicKeys, { isLoading: isDeleting }] = useDeletePublicKeysMutation();

    useBreadcrumbs([
        {
            text: t('navigation.account'),
            href: ROUTES.USER.LIST,
        },
        {
            text: paramUserName,
            href: ROUTES.USER.DETAILS.FORMAT(paramUserName),
        },
        {
            text: t('users.public_keys.title'),
            href: ROUTES.USER.PUBLIC_KEYS.FORMAT(paramUserName),
        },
    ]);

    const { items, collectionProps } = useCollection(publicKeys, {
        selection: {},
    });

    const { selectedItems = [] } = collectionProps;

    const openAddModal = () => {
        setKeyValue('');
        setKeyName('');
        setAddError('');
        setShowAddModal(true);
    };

    const closeAddModal = () => {
        setShowAddModal(false);
    };

    const handleAdd = () => {
        if (!keyValue.trim()) {
            setAddError(t('users.public_keys.key_required'));
            return;
        }

        addPublicKey({ key: keyValue.trim(), name: keyName.trim() || undefined })
            .unwrap()
            .then(() => {
                setShowAddModal(false);
            })
            .catch((error) => {
                const detail = (error?.data?.detail ?? []) as { msg: string; code: string }[];
                const isKeyExists = detail.some(({ code }) => code === 'resource_exists');
                setAddError(isKeyExists ? t('users.public_keys.key_already_exists') : getServerError(error));
            });
    };

    const handleDelete = () => {
        deletePublicKeys(selectedItems.map((k) => k.id))
            .unwrap()
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: getServerError(error) }),
                });
            });
    };

    const formatDate = (iso: string) => {
        return new Date(iso).toLocaleDateString(undefined, {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
        });
    };

    const columns = [
        {
            id: 'name',
            header: t('users.public_keys.name'),
            cell: (item: IPublicKey) => item.name,
        },
        {
            id: 'fingerprint',
            header: t('users.public_keys.fingerprint'),
            cell: (item: IPublicKey) => (
                <Box fontWeight="normal" variant="code">
                    {item.fingerprint}
                </Box>
            ),
        },
        {
            id: 'type',
            header: t('users.public_keys.key_type'),
            cell: (item: IPublicKey) => item.type,
        },
        {
            id: 'added_at',
            header: t('users.public_keys.added'),
            cell: (item: IPublicKey) => formatDate(item.added_at),
        },
    ];

    return (
        <>
            <Table
                {...collectionProps}
                loading={isLoading}
                columnDefinitions={columns}
                items={items}
                selectionType="multi"
                trackBy="id"
                header={
                    <Header
                        counter={publicKeys.length ? `(${publicKeys.length})` : undefined}
                        actions={
                            <SpaceBetween size="xs" direction="horizontal">
                                <ButtonWithConfirmation
                                    disabled={!selectedItems.length || isDeleting}
                                    onClick={handleDelete}
                                    confirmTitle={t('users.public_keys.delete_confirm_title')}
                                    confirmContent={t('users.public_keys.delete_confirm_message')}
                                >
                                    {t('common.delete')}
                                </ButtonWithConfirmation>

                                <Button variant="primary" onClick={openAddModal}>
                                    {t('users.public_keys.add_key')}
                                </Button>
                            </SpaceBetween>
                        }
                    >
                        {t('users.public_keys.title')}
                    </Header>
                }
                empty={
                    <Box textAlign="center" color="inherit">
                        <b>{t('users.public_keys.empty_title')}</b>
                        <Box padding={{ bottom: 's' }} variant="p" color="inherit">
                            {t('users.public_keys.empty_message')}
                        </Box>
                        <Button onClick={openAddModal}>{t('users.public_keys.add_key')}</Button>
                    </Box>
                }
            />

            <Modal
                visible={showAddModal}
                onDismiss={closeAddModal}
                header={t('users.public_keys.add_key')}
                footer={
                    <Box float="right">
                        <SpaceBetween direction="horizontal" size="xs">
                            <Button variant="link" onClick={closeAddModal}>
                                {t('common.cancel')}
                            </Button>
                            <Button variant="primary" loading={isAdding} onClick={handleAdd}>
                                {t('users.public_keys.add_key')}
                            </Button>
                        </SpaceBetween>
                    </Box>
                }
            >
                <SpaceBetween size="m">
                    <FormField
                        label={t('users.public_keys.key_name_label')}
                        description={t('users.public_keys.key_name_description')}
                    >
                        <CloudscapeInput
                            value={keyName}
                            onChange={({ detail }) => setKeyName(detail.value)}
                            placeholder={t('users.public_keys.key_name_placeholder')}
                        />
                    </FormField>

                    <FormField
                        label={t('users.public_keys.key_label')}
                        description={t('users.public_keys.key_description')}
                        errorText={addError}
                    >
                        <CloudscapeTextarea
                            value={keyValue}
                            onChange={({ detail }) => {
                                setKeyValue(detail.value);
                                setAddError('');
                            }}
                            placeholder="ssh-ed25519 AAAA..."
                            rows={5}
                        />
                    </FormField>
                </SpaceBetween>
            </Modal>
        </>
    );
};
