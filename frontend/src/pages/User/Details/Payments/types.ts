import React from 'react';

export interface IProps {
    payments: IPayment[];
    emptyMessageContent?: React.ReactNode;
    isLoading?: boolean;
    tableHeaderContent?: React.ReactNode;
}
