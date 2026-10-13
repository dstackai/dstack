import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { product } from 'product';

import { useBreadcrumbs } from 'hooks';
import { ROUTES } from 'routes';

import { convertMiBToGB, round } from './List/helpers';
import { Button, Header } from '../../components';
import { OfferList } from './List';

export const ListPage: React.FC = () => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const [selectedGpus, setSelectedGpus] = useState<IGpu[]>([]);
    const [noOffers, setNoOffers] = useState(false);

    useBreadcrumbs([
        {
            text: t('offer.title'),
            href: ROUTES.OFFERS.LIST,
        },
    ]);

    // Carries the filters over; a picked GPU narrows them to its name and memory.
    const launch = () => {
        const params = new URLSearchParams(searchParams);
        params.delete('group_by');

        const [gpu] = selectedGpus;

        if (gpu) {
            params.set('gpu_name', gpu.name);
            params.set('gpu_memory', `${round(convertMiBToGB(gpu.memory_mib))}GB`);
        }

        navigate(`${ROUTES.RUNS.LAUNCH}?${params}`);
    };

    // Selecting an offer only matters for templates.
    const selectionProps = product.hasTemplates
        ? {
              selectionType: 'single' as const,
              selectedItems: selectedGpus,
              onSelectionChange: ({ detail }: { detail: { selectedItems: IGpu[] } }) => setSelectedGpus(detail.selectedItems),
          }
        : {};

    return (
        <OfferList
            variant="full-page"
            showFleetFilter
            onChangeProjectName={() => setSelectedGpus([])}
            onChangeNoOffers={setNoOffers}
            {...selectionProps}
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
