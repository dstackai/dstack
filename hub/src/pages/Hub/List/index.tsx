import React, { useEffect, useMemo, useState } from 'react';
import {
    Cards,
    Header,
    SpaceBetween,
    Button,
    NavigateLink,
    TextFilter,
    Pagination,
    ListEmptyMessage,
    ConfirmationDialog,
} from 'components';
import { useAppSelector, useBreadcrumbs, useCollection } from 'hooks';
import { useDeleteHubsMutation, useGetHubsQuery } from 'services/hub';
import { ROUTES } from 'routes';
import { useTranslation } from 'react-i18next';
import { getHubRoleByUserName } from '../utils';
import { selectUserName } from 'App/slice';
import { useNavigate } from 'react-router-dom';

export const HubList: React.FC = () => {
    const { t } = useTranslation();
    const [showDeleteConfirm, setShowConfirmDelete] = useState(false);
    const userName = useAppSelector(selectUserName) ?? '';
    const { isLoading, data } = useGetHubsQuery();
    const navigate = useNavigate();
    const [deleteHubs, { isLoading: isDeleting }] = useDeleteHubsMutation();

    useBreadcrumbs([
        {
            text: t('navigation.hubs'),
            href: ROUTES.HUB.LIST,
        },
    ]);

    const toggleDeleteConfirm = () => {
        setShowConfirmDelete((val) => !val);
    };

    const renderEmptyMessage = (): React.ReactNode => {
        return <ListEmptyMessage title={t('hubs.empty_message_title')} message={t('hubs.empty_message_text')} />;
    };

    const renderNoMatchMessage = (onClearFilter: () => void): React.ReactNode => {
        return (
            <ListEmptyMessage title={t('hubs.nomatch_message_title')} message={t('hubs.nomatch_message_text')}>
                <Button onClick={onClearFilter}>{t('hubs.nomatch_message_button_label')}</Button>
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

    const deleteSelectedHubsHandler = () => {
        if (collectionProps.selectedItems?.length) deleteHubs(collectionProps.selectedItems.map((hub) => hub.hub_name));
        setShowConfirmDelete(false);
    };

    const editSelectedHubHandler = () => {
        if (collectionProps.selectedItems?.length === 1)
            navigate(ROUTES.HUB.EDIT_BACKEND.FORMAT(collectionProps.selectedItems[0].hub_name));
    };

    const addHubHandler = () => {
        navigate(ROUTES.HUB.ADD);
    };

    const renderCounter = () => {
        const { selectedItems } = collectionProps;

        if (!data?.length) return '';

        if (selectedItems?.length) return `(${selectedItems?.length}/${data?.length ?? 0})`;

        return `(${data.length})`;
    };

    const getIsTableItemDisabled = () => {
        return isDeleting;
    };

    const isDisabledEdit = useMemo(() => {
        if (collectionProps.selectedItems?.length !== 1) return true;

        return collectionProps.selectedItems?.some((item) => getHubRoleByUserName(item, userName) !== 'admin') ?? false;
    }, [isDeleting, collectionProps.selectedItems]);

    const isDisabledDelete = useMemo(() => {
        if (isDeleting || collectionProps.selectedItems?.length === 0) return true;

        return collectionProps.selectedItems?.some((item) => getHubRoleByUserName(item, userName) !== 'admin') ?? false;
    }, [isDeleting, collectionProps.selectedItems]);

    return (
        <>
            <Cards
                {...collectionProps}
                variant="full-page"
                cardDefinition={{
                    header: (hub) => (
                        <NavigateLink fontSize="heading-m" href={ROUTES.HUB.DETAILS.FORMAT(hub.hub_name)}>
                            {hub.hub_name}
                        </NavigateLink>
                    ),

                    sections: [
                        {
                            id: 'type',
                            header: t('hubs.card.backend'),
                            content: (hub) => t(`hubs.backend_type.${hub.backend.type}`),
                        },
                        {
                            id: 'region',
                            header: t('hubs.card.region'),
                            content: (hub) => hub.backend.region_name_title,
                        },
                        {
                            id: 'bucket',
                            header: t('hubs.card.bucket'),
                            content: (hub) => `${hub.backend.s3_bucket_name}`,
                        },
                    ],
                }}
                items={items}
                loading={isLoading}
                isItemDisabled={getIsTableItemDisabled}
                loadingText="Loading"
                selectionType="multi"
                header={
                    <Header
                        variant="awsui-h1-sticky"
                        counter={renderCounter()}
                        actions={
                            <SpaceBetween size="xs" direction="horizontal">
                                <Button onClick={addHubHandler}>{t('common.add')}</Button>
                                <Button onClick={editSelectedHubHandler} disabled={isDisabledEdit}>
                                    {t('common.edit')}
                                </Button>

                                <Button onClick={toggleDeleteConfirm} disabled={isDisabledDelete}>
                                    {t('common.delete')}
                                </Button>
                            </SpaceBetween>
                        }
                    >
                        {t('hubs.page_title')}
                    </Header>
                }
                filter={
                    <TextFilter
                        {...filterProps}
                        filteringPlaceholder={t('hubs.search_placeholder') || ''}
                        countText={t('common.match_count_with_value', { count: filteredItemsCount }) ?? ''}
                        disabled={isLoading}
                    />
                }
                pagination={<Pagination {...paginationProps} disabled={isLoading} />}
            />

            <ConfirmationDialog
                visible={showDeleteConfirm}
                onDiscard={toggleDeleteConfirm}
                onConfirm={deleteSelectedHubsHandler}
            />
        </>
    );
};
