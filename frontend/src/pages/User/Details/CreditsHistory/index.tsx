import React from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { Button, Header, InfoLink } from 'components';

import { useHelpPanel } from 'hooks';
import { ROUTES } from 'routes';
import { useGetUserPaymentsQuery } from 'services/user';

import { Payments } from '../Payments';
import { PAYMENTS_INFO } from './constants';

import { IProps } from './types';

export const CreditsHistory: React.FC<IProps> = ({ username }) => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const [openHelpPanel] = useHelpPanel();

    const { data, isLoading } = useGetUserPaymentsQuery({ username });

    const onAddClick = () => {
        navigate(ROUTES.USER.BILLING.ADD_PAYMENT.FORMAT(username));
    };

    return (
        <Payments
            payments={data ?? []}
            isLoading={isLoading}
            emptyMessageContent={<Button onClick={onAddClick}>{t('common.add')}</Button>}
            tableHeaderContent={
                <Header
                    actions={
                        <Button formAction="none" onClick={onAddClick}>
                            {t('common.add')}
                        </Button>
                    }
                    info={<InfoLink onFollow={() => openHelpPanel(PAYMENTS_INFO)} />}
                >
                    {t('users.manual_payments.title')}
                </Header>
            }
        />
    );
};
