import React from 'react';
import { useTranslation } from 'react-i18next';
import { format } from 'date-fns';

import { ListEmptyMessage, Pagination, Table } from 'components';

import { DATE_TIME_FORMAT } from 'consts';
import { useCollection } from 'hooks';
import { centsToFormattedString } from 'libs';

import { IProps } from './types';

export const Payments: React.FC<IProps> = ({ payments, emptyMessageContent, isLoading, tableHeaderContent }) => {
    const { t } = useTranslation();

    const renderEmptyMessage = (): React.ReactNode => {
        return (
            <ListEmptyMessage
                title={t('users.manual_payments.empty_message_title')}
                message={t('users.manual_payments.empty_message_text')}
            >
                {emptyMessageContent}
            </ListEmptyMessage>
        );
    };

    const { items, collectionProps, paginationProps } = useCollection(payments, {
        filtering: {
            empty: renderEmptyMessage(),
        },
        pagination: { pageSize: 20 },
        selection: {},
    });

    const columns = [
        {
            id: 'value',
            header: `${t('users.manual_payments.edit.value')}`,
            cell: (item: IPayment) => `${centsToFormattedString(item.value, '$')}`,
        },
        {
            id: 'created_at',
            header: t('users.manual_payments.edit.created_at'),
            cell: (item: IPayment) => format(new Date(item.created_at), DATE_TIME_FORMAT),
        },
        {
            id: 'description',
            header: `${t('users.manual_payments.edit.description')}`,
            cell: (item: IPayment) => item.description,
        },
    ];

    return (
        <Table
            {...collectionProps}
            columnDefinitions={columns}
            items={items}
            loading={isLoading}
            loadingText={t('common.loading')}
            stickyHeader={true}
            header={tableHeaderContent}
            pagination={<Pagination {...paginationProps} disabled={isLoading} />}
        />
    );
};
