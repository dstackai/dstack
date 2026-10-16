import React from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { Alert, Header, Loader } from 'components';

import { getServerError } from 'libs';
import { useGetFleetDetailsQuery } from 'services/fleet';

import { OfferList } from 'pages/Offers/List';

export const FleetOffers = () => {
    const { t } = useTranslation();
    const { projectName = '', fleetId = '' } = useParams();
    const { currentData: fleet, error } = useGetFleetDetailsQuery({ projectName, fleetId });

    if (error) {
        return <Alert type="error">{t('common.server_error', { error: getServerError(error) })}</Alert>;
    }

    if (!fleet) {
        return <Loader />;
    }

    // Offer APIs identify active fleets by name; a terminated fleet's name may have been reused.
    if (fleet.status === 'terminated') {
        return <Alert type="info">{t('offer.terminated_fleet')}</Alert>;
    }

    return (
        <OfferList
            key={`${projectName}/${fleetId}`}
            permanentFilters={{ project_name: projectName, fleet: fleet.name }}
            allowUngrouped
            header={<Header variant="h2">{t('offer.title')}</Header>}
        />
    );
};
