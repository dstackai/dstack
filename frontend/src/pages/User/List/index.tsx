import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { Box, Button, ConfirmationDialog, Header, ListEmptyMessage, Loader, SpaceBetween, Table, TextFilter } from 'components';

import { DEFAULT_TABLE_PAGE_SIZE } from 'consts';
import { useAppSelector, useBreadcrumbs, useCollection, useInfiniteScroll, useNotifications } from 'hooks';
import { getServerError } from 'libs';
import { ROUTES } from 'routes';
import { useDeleteUsersMutation, useLazyGetUserListQuery } from 'services/user';

import { selectUserData } from 'App/slice';

import { useColumnDefinitions } from './hooks';

export const UserList: React.FC = () => {
    const { t } = useTranslation();
    const [showDeleteConfirm, setShowConfirmDelete] = useState(false);
    const [filteringText, setFilteringText] = useState('');
    const [namePattern, setNamePattern] = useState<string>('');
    const userData = useAppSelector(selectUserData);
    const userGlobalRole = userData?.global_role ?? '';
    const [deleteUsers, { isLoading: isDeleting }] = useDeleteUsersMutation();
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();

    const { data, isLoading, refreshList, isLoadingMore, totalCount } = useInfiniteScroll<IUser, TGetUserListParams>({
        useLazyQuery: useLazyGetUserListQuery,
        args: { name_pattern: namePattern, limit: DEFAULT_TABLE_PAGE_SIZE },

        getPaginationParams: (lastUser) => ({
            prev_created_at: lastUser.created_at,
        }),
    });

    useBreadcrumbs([
        {
            text: t('navigation.account'),
            href: ROUTES.USER.LIST,
        },
    ]);

    const columns = useColumnDefinitions();

    const toggleDeleteConfirm = () => {
        setShowConfirmDelete((val) => !val);
    };

    const addUserHandler = () => {
        navigate(ROUTES.USER.ADD);
    };

    const onClearFilter = () => {
        setNamePattern('');
        setFilteringText('');
    };

    const renderEmptyMessage = (): React.ReactNode => {
        if (isLoading) {
            return null;
        }

        if (filteringText) {
            return (
                <ListEmptyMessage title={t('users.nomatch_message_title')} message={t('users.nomatch_message_text')}>
                    <Button onClick={onClearFilter}>{t('common.clearFilter')}</Button>
                </ListEmptyMessage>
            );
        }

        return (
            <ListEmptyMessage title={t('users.empty_message_title')} message={t('projects.empty_message_text')}>
                <Button onClick={addUserHandler}>{t('common.add')}</Button>
            </ListEmptyMessage>
        );
    };

    const { items, actions, collectionProps } = useCollection(data, {
        filtering: {
            empty: renderEmptyMessage(),
        },
        selection: {},
    });

    const deleteSelectedUserHandler = () => {
        const { selectedItems } = collectionProps;
        if (selectedItems?.length) {
            deleteUsers(selectedItems.map((user) => user.username))
                .unwrap()
                .then(() => actions.setSelectedItems([]))
                .catch((error) => {
                    pushNotification({
                        type: 'error',
                        content: t('common.server_error', { error: getServerError(error) }),
                    });
                });
        }
        setShowConfirmDelete(false);
    };

    const editSelectedUserHandler = () => {
        const { selectedItems } = collectionProps;

        if (selectedItems?.length) navigate(ROUTES.USER.EDIT.FORMAT(selectedItems[0].username));
    };

    const getIsTableItemDisabled = () => {
        return isDeleting;
    };

    const isDisabledDelete = useMemo(() => {
        return isDeleting || collectionProps.selectedItems?.length === 0 || userGlobalRole !== 'admin';
    }, [collectionProps.selectedItems]);

    const isDisabledEdit = useMemo(() => {
        return isDeleting || collectionProps.selectedItems?.length !== 1 || userGlobalRole !== 'admin';
    }, [collectionProps.selectedItems]);

    const renderCounter = () => {
        if (typeof totalCount !== 'number') return '';

        return `(${totalCount})`;
    };

    return (
        <>
            <Table
                {...collectionProps}
                variant="full-page"
                isItemDisabled={getIsTableItemDisabled}
                // eslint-disable-next-line @typescript-eslint/ban-ts-comment
                // @ts-expect-error
                columnDefinitions={columns}
                items={items}
                loading={isLoading}
                loadingText={t('common.loading')}
                selectionType="multi"
                stickyHeader={true}
                header={
                    <Header
                        variant="awsui-h1-sticky"
                        counter={renderCounter()}
                        actions={
                            <SpaceBetween size="xs" direction="horizontal">
                                <Button formAction="none" onClick={editSelectedUserHandler} disabled={isDisabledEdit}>
                                    {t('common.edit')}
                                </Button>

                                <Button formAction="none" onClick={toggleDeleteConfirm} disabled={isDisabledDelete}>
                                    {t('common.delete')}
                                </Button>

                                <Button formAction="none" onClick={addUserHandler} disabled={userGlobalRole !== 'admin'}>
                                    {t('common.add')}
                                </Button>

                                <Button
                                    iconName="refresh"
                                    disabled={isLoading}
                                    ariaLabel={t('common.refresh')}
                                    onClick={refreshList}
                                />
                            </SpaceBetween>
                        }
                    >
                        {t('users.page_title')}
                    </Header>
                }
                filter={
                    <TextFilter
                        filteringText={filteringText}
                        onChange={({ detail }) => setFilteringText(detail.filteringText)}
                        onDelayedChange={() => setNamePattern(filteringText)}
                        filteringPlaceholder={t('users.search_placeholder')}
                        disabled={isLoading}
                    />
                }
                footer={<Loader show={isLoadingMore} padding={{ vertical: 'm' }} />}
            />

            <ConfirmationDialog
                visible={showDeleteConfirm}
                content={<Box variant="span">{t('confirm_dialog.message')}</Box>}
                onDiscard={toggleDeleteConfirm}
                onConfirm={deleteSelectedUserHandler}
                confirmButtonLabel={t('common.delete')}
            />
        </>
    );
};
