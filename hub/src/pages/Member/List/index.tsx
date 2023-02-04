import React, { useEffect, useMemo } from 'react';
import { Button, Table, Header, Pagination, SpaceBetween, TextFilter, NavigateLink, ListEmptyMessage } from 'components';
import { useDeleteUsersMutation, useGetUserListQuery } from 'services/user';
import { useCollection } from 'hooks';
import { ROUTES } from 'routes';
import { useTranslation } from 'react-i18next';

export const MemberList: React.FC = () => {
    const { t } = useTranslation();
    const { isLoading, data } = useGetUserListQuery();
    const [deleteUsers, { isLoading: isDeleting }] = useDeleteUsersMutation();

    const COLUMN_DEFINITIONS = [
        {
            id: 'name',
            header: 'User name',
            cell: (item: IUser) => (
                <NavigateLink href={ROUTES.MEMBER.DETAILS.FORMAT(item.user_name)}>{item.user_name}</NavigateLink>
            ),
        },
        {
            id: 'email',
            header: 'Email',
            cell: (item: IUser) => item.email,
        },
        {
            id: 'token',
            header: 'Token',
            cell: (item: IUser) => item.token,
        },
        {
            id: 'permission_level',
            header: 'Permission Level',
            cell: (item: IUser) => item.permission_level,
        },
    ];

    const renderEmptyMessage = (): React.ReactNode => {
        return <ListEmptyMessage title={t('users.empty_message_title')} message={t('hubs.empty_message_text')} />;
    };

    const renderNoMatchMessage = (onClearFilter: () => void): React.ReactNode => {
        return (
            <ListEmptyMessage title={t('users.nomatch_message_title')} message={t('users.nomatch_message_text')}>
                <Button onClick={onClearFilter}>{t('users.nomatch_message_button_label')}</Button>
            </ListEmptyMessage>
        );
    };

    const { items, actions, filteredItemsCount, collectionProps, filterProps, paginationProps } = useCollection(data ?? [], {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderNoMatchMessage(() => actions.setFiltering('')),
        },
        pagination: { pageSize: 20 },
        selection: {},
    });

    useEffect(() => {
        if (!isDeleting) actions.setSelectedItems([]);
    }, [isDeleting]);

    const deleteSelectedUserHandler = () => {
        const { selectedItems } = collectionProps;

        if (selectedItems?.length) deleteUsers(selectedItems.map((user) => user.user_name));
    };

    const getIsTableItemDisabled = () => {
        return isDeleting;
    };

    const isDisabledDelete = useMemo(() => {
        return isDeleting || collectionProps.selectedItems?.length === 0;
    }, [collectionProps.selectedItems]);

    const isDisabledEdit = useMemo(() => {
        return isDeleting || collectionProps.selectedItems?.length !== 1;
    }, [collectionProps.selectedItems]);

    const renderCounter = () => {
        const { selectedItems } = collectionProps;

        if (!data?.length) return '';

        if (selectedItems?.length) return `(${selectedItems?.length}/${data?.length ?? 0})`;

        return `(${data.length})`;
    };

    return (
        <Table
            {...collectionProps}
            variant="full-page"
            isItemDisabled={getIsTableItemDisabled}
            columnDefinitions={COLUMN_DEFINITIONS}
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
                            <Button disabled={isDisabledEdit}>{t('common.edit')}</Button>

                            <Button onClick={deleteSelectedUserHandler} disabled={isDisabledDelete}>
                                {t('common.delete')}
                            </Button>
                            <Button>{t('common.add')}</Button>
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
    );
};
