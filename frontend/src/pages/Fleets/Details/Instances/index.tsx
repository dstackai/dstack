import React from 'react';
import { useTranslation } from 'react-i18next';

import { Header, ListEmptyMessage, Table } from 'components';

import { useCollection } from 'hooks';

import { useColumnsDefinitions } from './hooks';

export interface Props {
    data: IInstance[];
}

export const Instances: React.FC<Props> = ({ data }) => {
    const { t } = useTranslation();

    const { columns } = useColumnsDefinitions();

    const renderEmptyMessage = (): React.ReactNode => {
        return (
            <ListEmptyMessage
                title={t('pools.instances.empty_message_title')}
                message={t('pools.instances.empty_message_text')}
            />
        );
    };

    const { items, collectionProps } = useCollection(data ?? [], {
        filtering: {
            empty: renderEmptyMessage(),
            noMatch: renderEmptyMessage(),
        },
        selection: {},
    });

    const renderCounter = () => {
        if (!data?.length) return '';

        return `(${data.length})`;
    };

    return (
        <Table
            {...collectionProps}
            columnDefinitions={columns}
            items={items}
            // selectionType="multi"
            stickyHeader={true}
            header={<Header counter={renderCounter()}>{t('pools.instances.title')}</Header>}
        />
    );
};
