import React, { useState } from 'react';
import { Box, Cards, Header, SpaceBetween, Button, NavigateLink, Link, TextFilter, Pagination } from 'components';
import { useCollection } from 'hooks';
import { useGetHubsQuery } from 'services/hub';
import { ROUTES } from 'routes';
import styles from './styles.module.scss';
import { useTranslation } from 'react-i18next';

export const HubList: React.FC = () => {
    const { t } = useTranslation();
    const { isLoading, data } = useGetHubsQuery();
    const [selectedItems, setSelectedItems] = useState<IHub[]>([]);

    const { items, filterProps, paginationProps } = useCollection(data ?? [], {
        filtering: {
            // empty: <TableEmptyState resourceName="Distribution" />,
            // noMatch: <TableNoMatchState onClearFilter={() => actions.setFiltering('')} />,
        },
        pagination: { pageSize: 20 },
        selection: {},
    });

    const renderEmptyMessage = () => {
        return (
            <Box textAlign="center" color="inherit">
                <b>No hubs</b>
                <Box padding={{ bottom: 's' }} variant="p" color="inherit">
                    No hubs to display.
                </Box>
            </Box>
        );
    };

    const renderCounter = () => {
        if (!data?.length) return '';

        if (selectedItems.length) return `(${selectedItems.length}/${data?.length ?? 0})`;

        return `(${data?.length ?? 0})`;
    };

    return (
        <Cards
            variant="full-page"
            onSelectionChange={({ detail }) => setSelectedItems(detail.selectedItems)}
            selectedItems={selectedItems}
            cardDefinition={{
                header: (e) => (
                    <NavigateLink fontSize="heading-m" href={ROUTES.HUB.DETAILS.FORMAT(e.name)}>
                        {e.name}
                    </NavigateLink>
                ),

                sections: [
                    {
                        id: 'actions',
                        header: '',
                        content: () => (
                            <div className={styles.cardFooter}>
                                <SpaceBetween data-selector="card-buttons" direction="horizontal" size="m">
                                    <div />
                                    <Link onFollow={() => console.log('edit')}>{t('common.edit')}</Link>
                                </SpaceBetween>
                            </div>
                        ),
                    },
                ],
            }}
            items={items}
            loading={isLoading}
            loadingText="Loading"
            selectionType="multi"
            empty={renderEmptyMessage()}
            header={
                <Header
                    variant="awsui-h1-sticky"
                    counter={renderCounter()}
                    actions={
                        <SpaceBetween size="xs" direction="horizontal">
                            <Button disabled={selectedItems.length !== 1}>Edit</Button>
                            <Button disabled={selectedItems.length === 0}>Delete</Button>
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
                    // TODO Show filter counter
                    // countText={getFilterCounterText(filteredItemsCount)}
                    disabled={isLoading}
                />
            }
            pagination={<Pagination {...paginationProps} disabled={isLoading} />}
        />
    );
};
