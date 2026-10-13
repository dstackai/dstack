import React from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useParams } from 'react-router-dom';
import { product } from 'product';

import { Alert, Container, Loader } from 'components';

import { useBreadcrumbs } from 'hooks';
import { ROUTES } from 'routes';
import { useGetProjectQuery } from 'services/project';

import { QuotasTable } from '../../components/QuotasTable';
import { useCheckAvailableProjectPermission } from '../../hooks/useCheckAvailableProjectPermission';

export const ProjectQuotas: React.FC = () => {
    const { t } = useTranslation();
    const { projectName = '' } = useParams();
    const { currentData: project, error } = useGetProjectQuery(
        { name: projectName },
        { skip: !product.hasBilling, refetchOnMountOrArgChange: false },
    );
    const { isProjectAdmin } = useCheckAvailableProjectPermission();

    useBreadcrumbs([
        { text: t('navigation.project_other'), href: ROUTES.PROJECT.LIST },
        { text: projectName, href: ROUTES.PROJECT.DETAILS.FORMAT(projectName) },
        { text: 'Quotas', href: ROUTES.PROJECT.DETAILS.QUOTAS.FORMAT(projectName) },
    ]);

    if (!product.hasBilling) {
        return <Navigate to={ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(projectName)} replace />;
    }

    if (error && !project) {
        return <Alert type="error">Unable to load project.</Alert>;
    }

    if (!project) {
        return (
            <Container>
                <Loader />
            </Container>
        );
    }

    if (!isProjectAdmin(project)) {
        return <Navigate to={ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(projectName)} replace />;
    }

    return <QuotasTable key={projectName} projectName={projectName} />;
};
