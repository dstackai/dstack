import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { format } from 'date-fns';

import {
    Button,
    ConfirmationDialog,
    Header,
    Link,
    ListEmptyMessage,
    NavigateLink,
    Pagination,
    SpaceBetween,
    Table,
    TextFilter,
} from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { useAppSelector, useBreadcrumbs, useCollection, useNotifications } from 'hooks';
import { getServerError, includeSubString } from 'libs';
import { ROUTES } from 'routes';
import { useDeleteUsersMutation, useGetUserListQuery } from 'services/user';

import { selectUserData } from 'App/slice';

export const UserList: React.FC = () => {
    const { t } = useTranslation();
    const [showDeleteConfirm, setShowConfirmDelete] = useState(false);
    const userData = useAppSelector(selectUserData);
    const userGlobalRole = userData?.global_role ?? '';
    const { isLoading, isFetching, data, refetch } = useGetUserListQuery();
    const [deleteUsers, { isLoading: isDeleting }] = useDeleteUsersMutation();
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();

    const sortedData = useMemo<IUser[]>(() => {
        if (!data) return [];

        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-ignore
        return [...data].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    }, [data]);

    useBreadcrumbs([
        {
            text: t('navigation.account'),
            href: ROUTES.USER.LIST,
        },
    ]);

    const COLUMN_DEFINITIONS = [
        {
            id: 'name',
            header: t('users.user_name'),
            cell: (item: IUser) => (
                <NavigateLink href={ROUTES.USER.DETAILS.FORMAT(item.username)}>{item.username}</NavigateLink>
            ),
        },
        {
            id: 'email',
            header: t('users.email'),
            cell: (item: IUser) => (item.email ? <Link href={`mailto:${item.email}`}>{item.email}</Link> : '-'),
        },
        {
            id: 'global_role',
            header: t('users.global_role'),
            cell: (item: IUser) => t(`roles.${item.global_role}`),
        },
        process.env.UI_VERSION === 'sky' && {
            id: 'created_at',
            header: t('users.created_at'),
            cell: (item: IUser) => format(new Date(item.created_at), DATE_TIME_FORMAT),
        },
    ].filter(Boolean);

    const toggleDeleteConfirm = () => {
        setShowConfirmDelete((val) => !val);
    };

    const addUserHandler = () => {
        navigate(ROUTES.USER.ADD);
    };

    const renderEmptyMessage = (): React.ReactNode => {
        return (
            <ListEmptyMessage title={t('users.empty_message_title')} message={t('projects.empty_message_text')}>
                <Button onClick={addUserHandler}>{t('common.add')}</Button>
            </ListEmptyMessage>
        );
    };

    const renderNoMatchMessage = (onClearFilter: () => void): React.ReactNode => {
        return (
            <ListEmptyMessage title={t('users.nomatch_message_title')} message={t('users.nomatch_message_text')}>
                <Button onClick={onClearFilter}>{t('common.clearFilter')}</Button>
            </ListEmptyMessage>
        );
    };

    const { items, actions, filteredItemsCount, collectionProps, filterProps, paginationProps } = useCollection(sortedData, {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(() => actions.setFiltering('')),
            filteringFunction: (user, filteringText) =>
                includeSubString(user.username, filteringText) || includeSubString(user.email ?? '', filteringText),
        },
        pagination: { pageSize: 20 },
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
        const { selectedItems } = collectionProps;

        if (!data?.length) return '';

        if (selectedItems?.length) return `(${selectedItems?.length}/${data?.length ?? 0})`;

        return `(${data.length})`;
    };

    return (
        <>
            <Table
                {...collectionProps}
                variant="full-page"
                isItemDisabled={getIsTableItemDisabled}
                columnDefinitions={COLUMN_DEFINITIONS}
                items={items}
                loading={isLoading || isFetching}
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
                                    disabled={isLoading || isFetching}
                                    ariaLabel={t('common.refresh')}
                                    onClick={refetch}
                                />
                            </SpaceBetween>
                        }
                    >
                        {t('users.page_title')}
                    </Header>
                }
                filter={
                    <TextFilter
                        {...filterProps}
                        filteringPlaceholder={t('users.search_placeholder')}
                        countText={t('common.match_count_with_value', { count: filteredItemsCount })}
                        disabled={isLoading}
                    />
                }
                pagination={<Pagination {...paginationProps} disabled={isLoading} />}
            />

            <ConfirmationDialog
                visible={showDeleteConfirm}
                onDiscard={toggleDeleteConfirm}
                onConfirm={deleteSelectedUserHandler}
            />
        </>
    );
};
