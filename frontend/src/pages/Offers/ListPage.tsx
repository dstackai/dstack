import React from 'react';
import { useTranslation } from 'react-i18next';

import { useBreadcrumbs } from 'hooks';
import { ROUTES } from 'routes';

import { Header } from '../../components';
import { OfferList } from './List';

export const ListPage: React.FC = () => {
    const { t } = useTranslation();

    useBreadcrumbs([
        {
            text: t('offer.title'),
            href: ROUTES.OFFERS.LIST,
        },
    ]);

    return <OfferList variant="full-page" header={<Header variant="awsui-h1-sticky">{t('offer.title')}</Header>} />;
};
