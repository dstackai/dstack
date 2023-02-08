import React, { useEffect, useMemo } from 'react';
import { Box, Cards, Header, SpaceBetween, Button, NavigateLink, TextFilter, Pagination } from 'components';
import { useCollection } from 'hooks';
import { useDeleteHubsMutation, useGetHubsQuery } from 'services/hub';
import { ROUTES } from 'routes';
import { useTranslation } from 'react-i18next';

export const HubList: React.FC = () => {
    const { t } = useTranslation();
    const { isLoading, data } = useGetHubsQuery();
    const [deleteHubs, { isLoading: isDeleting }] = useDeleteHubsMutation();
    const renderEmptyMessage = (): React.ReactNode => {
        return (
            <Box textAlign="center" color="inherit">
                <b>{t('hubs.empty_message_title')}</b>
                <Box padding={{ bottom: 's' }} variant="p" color="inherit">
                    {t('hubs.empty_message_text')}
                </Box>
            </Box>
        );
    };

    const renderNoMatchMessage = (onClearFilter: () => void): React.ReactNode => {
        return (
            <Box textAlign="center" color="inherit">
                <b>{t('hubs.nomatch_message_title')}</b>
                <Box padding={{ bottom: 's' }} variant="p" color="inherit">
                    {t('hubs.nomatch_message_text')}
                </Box>

                <Button onClick={onClearFilter}>{t('hubs.nomatch_message_button_label')}</Button>
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

    useEffect(() => {
        if (!isDeleting) actions.setSelectedItems([]);
    }, [isDeleting]);

    const deleteSelectedHubsHandler = () => {
        if (collectionProps.selectedItems?.length) deleteHubs(collectionProps.selectedItems.map((hub) => hub.hub_name));
    };

    const renderCounter = () => {
        const { selectedItems } = collectionProps;

        if (!data?.length) return '';

        if (selectedItems?.length) return `(${selectedItems?.length}/${data?.length ?? 0})`;

        return `(${data.length})`;
    };

    const isDisabledEdit = useMemo(() => {
        if (collectionProps.selectedItems?.length !== 1) return true;

        return collectionProps.selectedItems?.some((item) => item.permission !== 'write') ?? false;
    }, [isDeleting, collectionProps.selectedItems]);

    const isDisabledDelete = useMemo(() => {
        if (isDeleting || collectionProps.selectedItems?.length === 0) return true;

        return collectionProps.selectedItems?.some((item) => item.permission !== 'write') ?? false;
    }, [isDeleting, collectionProps.selectedItems]);

    return (
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
                        header: t('hubs.card.type'),
                        content: (hub) => hub.type,
                    },
                    {
                        id: 'region',
                        header: t('hubs.card.region'),
                        content: (hub) => hub.region,
                    },
                    {
                        id: 'bucket',
                        header: t('hubs.card.bucket'),
                        content: (hub) => hub.bucket,
                    },
                ],
            }}
            items={items}
            loading={isLoading}
            loadingText="Loading"
            selectionType="multi"
            header={
                <Header
                    variant="awsui-h1-sticky"
                    counter={renderCounter()}
                    actions={
                        <SpaceBetween size="xs" direction="horizontal">
                            <Button>{t('common.add')}</Button>
                            <Button disabled={isDisabledEdit}>{t('common.edit')}</Button>

                            <Button onClick={deleteSelectedHubsHandler} disabled={isDisabledDelete}>
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
    );
};
