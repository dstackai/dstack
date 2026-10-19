import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { product } from 'product';

import { useBreadcrumbs } from 'hooks';
import { ROUTES } from 'routes';

import { getOfferSearchParams, OfferCard } from './List/helpers';
import { Button, Header } from '../../components';
import { OfferList } from './List';

export const ListPage: React.FC = () => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const [selectedOffers, setSelectedOffers] = useState<OfferCard[]>([]);
    const [noOffers, setNoOffers] = useState(false);

    useBreadcrumbs([
        {
            text: t('offer.title'),
            href: ROUTES.OFFERS.LIST,
        },
    ]);

    const launch = () => {
        const params = getOfferSearchParams(searchParams, selectedOffers[0]);
        navigate(`${ROUTES.RUNS.LAUNCH}?${params}`);
    };

    return (
        <OfferList
            variant="full-page"
            showFleetFilter
            allowUngrouped
            onChangeFilters={() => setSelectedOffers([])}
            onChangeNoOffers={setNoOffers}
            selectionType={product.hasTemplates ? 'single' : undefined}
            selectedItems={selectedOffers}
            onSelectionChange={({ detail }) => setSelectedOffers(detail.selectedItems)}
            header={
                <Header
                    variant="awsui-h1-sticky"
                    actions={
                        // Nothing to launch on without offers, e.g. when no backend is configured.
                        <Button variant="primary" disabled={noOffers} onClick={launch}>
                            {t('runs.launch_button')}
                        </Button>
                    }
                >
                    {t('offer.title')}
                </Header>
            }
        />
    );
};
