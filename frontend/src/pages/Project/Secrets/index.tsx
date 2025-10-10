import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button, ButtonWithConfirmation, Header, ListEmptyMessage, Modal, Pagination, SpaceBetween, Table } from 'components';

import { useAppSelector, useCollection, useNotifications, usePermissionGuard } from 'hooks';
import { getServerError } from 'libs';
import {
    useDeleteSecretsMutation,
    useGetAllSecretsQuery,
    useLazyGetSecretQuery,
    useUpdateSecretMutation,
} from 'services/secrets';
import { GlobalUserRole, ProjectUserRole } from 'types';

import { selectUserData } from 'App/slice';

import { getProjectRoleByUserName } from '../utils';
import { SecretForm } from './Form';

import { IProps, TFormValues } from './types';

import styles from './styles.module.scss';

export const ProjectSecrets: React.FC<IProps> = ({ project, loading }) => {
    const { t } = useTranslation();
    const userData = useAppSelector(selectUserData);
    const userName = userData?.username ?? '';
    const [initialFormValues, setInitialFormValues] = useState<TFormValues | undefined>();
    const projectName = project?.project_name ?? '';
    const [pushNotification] = useNotifications();

    const [hasPermissionForSecretsManaging] = usePermissionGuard({
        allowedProjectRoles: [ProjectUserRole.ADMIN],
        allowedGlobalRoles: [GlobalUserRole.ADMIN],
        projectRole: project ? (getProjectRoleByUserName(project, userName) ?? undefined) : undefined,
    });

    const { data, isLoading, isFetching } = useGetAllSecretsQuery(
        { project_name: projectName },
        { skip: !hasPermissionForSecretsManaging },
    );
    const [updateSecret, { isLoading: isUpdating }] = useUpdateSecretMutation();
    const [deleteSecret, { isLoading: isDeleting }] = useDeleteSecretsMutation();
    const [getSecret, { isLoading: isGettingSecrets }] = useLazyGetSecretQuery();

    const { items, paginationProps, collectionProps } = useCollection(data ?? [], {
        filtering: {
            empty: hasPermissionForSecretsManaging ? (
                <ListEmptyMessage
                    title={t('projects.edit.secrets.empty_message_title')}
                    message={t('projects.edit.secrets.empty_message_text')}
                />
            ) : (
                <ListEmptyMessage
                    title={t('projects.edit.secrets.not_permissions_title')}
                    message={t('projects.edit.secrets.not_permissions_description')}
                />
            ),
        },
        pagination: { pageSize: 10 },
        selection: {},
    });

    const { selectedItems } = collectionProps;

    const deleteSelectedSecrets = () => {
        const names = selectedItems?.map((s) => s.name ?? '');

        if (names?.length) {
            deleteSecret({ project_name: projectName, names });
        }
    };

    const removeSecretByName = (name: IProjectSecret['name']) => {
        deleteSecret({ project_name: projectName, names: [name] });
    };

    const updateOrCreateSecret = ({ name, value }: TFormValues) => {
        if (!name || !value) {
            return;
        }

        updateSecret({ project_name: projectName, name, value })
            .unwrap()
            .then(() => setInitialFormValues(undefined))
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: getServerError(error) }),
                });
            });
    };

    const editSecret = ({ name }: IProjectSecret) => {
        getSecret({ project_name: projectName, name })
            .unwrap()
            .then((secret) => setInitialFormValues(secret));
    };

    const closeModal = () => setInitialFormValues(undefined);

    const isDisabledActions = loading || isLoading || isFetching || isDeleting || isGettingSecrets;

    const COLUMN_DEFINITIONS = [
        {
            id: 'name',
            header: t('projects.edit.secrets.name'),
            cell: (secret: IProjectSecret) => secret.name,
        },
        {
            id: 'value',
            header: t('projects.edit.secrets.value'),
            cell: (secret: IProjectSecret) => {
                return (
                    <div className={styles.value}>
                        <div className={styles.valueFieldWrapper}>************************</div>

                        <div className={styles.buttonsWrapper}>
                            <Button
                                disabled={isDisabledActions}
                                formAction="none"
                                onClick={() => editSecret(secret)}
                                variant="icon"
                                iconName="edit"
                            />

                            <ButtonWithConfirmation
                                disabled={isDisabledActions}
                                formAction="none"
                                onClick={() => removeSecretByName(secret.name)}
                                confirmTitle={t('projects.edit.secrets.delete_confirm_title')}
                                confirmContent={t('projects.edit.secrets.delete_confirm_message', { name: secret.name })}
                                variant="icon"
                                iconName="remove"
                            />
                        </div>
                    </div>
                );
            },
        },
    ];

    const addSecretHandler = () => {
        setInitialFormValues({});
    };

    const renderActions = () => {
        if (!hasPermissionForSecretsManaging) {
            return null;
        }

        const actions = [
            <Button key="add" formAction="none" onClick={addSecretHandler}>
                {t('common.add')}
            </Button>,

            <ButtonWithConfirmation
                key="delete"
                disabled={isDisabledActions || !selectedItems?.length}
                formAction="none"
                onClick={deleteSelectedSecrets}
                confirmTitle={t('projects.edit.secrets.multiple_delete_confirm_title')}
                confirmContent={t('projects.edit.secrets.multiple_delete_confirm_message', { count: selectedItems?.length })}
            >
                {t('common.delete')}
            </ButtonWithConfirmation>,
        ];

        return actions.length > 0 ? (
            <SpaceBetween size="xs" direction="horizontal">
                {actions}
            </SpaceBetween>
        ) : undefined;
    };

    const isShowModal = !!initialFormValues;

    return (
        <>
            <Table
                {...collectionProps}
                selectionType="multi"
                columnDefinitions={COLUMN_DEFINITIONS}
                items={items}
                loading={isLoading}
                header={
                    <Header
                        variant="h2"
                        counter={hasPermissionForSecretsManaging ? `(${items?.length})` : ''}
                        actions={renderActions()}
                    >
                        {t('projects.edit.secrets.section_title')}
                    </Header>
                }
                pagination={<Pagination {...paginationProps} />}
            />

            {hasPermissionForSecretsManaging && (
                <Modal
                    header={
                        initialFormValues?.id
                            ? t('projects.edit.secrets.update_secret')
                            : t('projects.edit.secrets.create_secret')
                    }
                    visible={isShowModal}
                    onDismiss={closeModal}
                >
                    {isShowModal && (
                        <SecretForm
                            initialValues={initialFormValues}
                            onSubmit={updateOrCreateSecret}
                            loading={isLoading || isUpdating}
                            onCancel={closeModal}
                        />
                    )}
                </Modal>
            )}
        </>
    );
};
