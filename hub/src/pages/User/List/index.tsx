import React, { useMemo } from 'react';
import { Button, Table, Header, Pagination, SpaceBetween, TextFilter, NavigateLink, Box } from 'components';
import { useGetUserListQuery } from 'services/user';
import { useCollection } from 'hooks';
import { ROUTES } from 'routes';
import { useTranslation } from 'react-i18next';

export const UserList: React.FC = () => {
    const { t } = useTranslation();
    const { isLoading, data } = useGetUserListQuery();

    const COLUMN_DEFINITIONS = [
        {
            id: 'name',
            header: 'User name',
            cell: (item: IUser) => (
                <NavigateLink href={ROUTES.USER.DETAILS.FORMAT(item.user_name)}>{item.user_name}</NavigateLink>
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
        return (
            <Box textAlign="center" color="inherit">
                <b>{t('users.empty_message_title')}</b>
                <Box padding={{ bottom: 's' }} variant="p" color="inherit">
                    {t('hubs.empty_message_text')}
                </Box>
            </Box>
        );
    };

    const renderNoMatchMessage = (onClearFilter: () => void): React.ReactNode => {
        return (
            <Box textAlign="center" color="inherit">
                <b>{t('users.nomatch_message_title')}</b>
                <Box padding={{ bottom: 's' }} variant="p" color="inherit">
                    {t('users.nomatch_message_text')}
                </Box>

                <Button onClick={onClearFilter}>{t('users.nomatch_message_button_label')}</Button>
            </Box>
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

    const deleteSelectedUserHandler = () => {
        return null;
    };

    const isDisabledDelete = useMemo(() => {
        return collectionProps.selectedItems?.length === 0;
    }, [collectionProps.selectedItems]);

    const isDisabledEdit = useMemo(() => {
        return collectionProps.selectedItems?.length !== 1;
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
            columnDefinitions={COLUMN_DEFINITIONS}
            items={items}
            loading={isLoading}
            loadingText={t('common.loading') ?? ''}
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
                    filteringPlaceholder={t('users.search_placeholder') || ''}
                    countText={t('common.match_count_with_value', { count: filteredItemsCount }) ?? ''}
                    disabled={isLoading}
                />
            }
            pagination={<Pagination {...paginationProps} disabled={isLoading} />}
        />
    );
};
