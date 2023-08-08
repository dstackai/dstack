import React from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import { Container, Header } from 'components';

import { useBreadcrumbs, useNotifications } from 'hooks';
import { ROUTES } from 'routes';
import { useCreateBackendMutation } from 'services/backend';

import { BackendForm } from '../Form';

export const BackendAdd: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.name ?? '';
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();

    const [createBackend, { isLoading }] = useCreateBackendMutation();

    useBreadcrumbs([
        {
            text: t('navigation.projects'),
            href: ROUTES.PROJECT.LIST,
        },
        {
            text: paramProjectName,
            href: ROUTES.PROJECT.DETAILS.REPOSITORIES.FORMAT(paramProjectName),
        },
        {
            text: t('projects.settings'),
            href: ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName),
        },
        {
            text: t('backend.add_page_title_one'),
            href: ROUTES.PROJECT.BACKEND.ADD.FORMAT(paramProjectName),
        },
    ]);

    const onCancelHandler = () => {
        navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName));
    };

    const onSubmitHandler = (backend: TBackendConfig) => {
        const request = createBackend({
            projectName: paramProjectName,
            config: backend,
        }).unwrap();

        request
            .then(() => {
                pushNotification({
                    type: 'success',
                    content: t('projects.create.success_notification'),
                });

                navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName));
            })
            .catch((error) => console.log(error));

        return request;
    };

    return (
        <Container header={<Header variant="h2">{t('backend.add_page_title_one')}</Header>}>
            <BackendForm loading={isLoading} onSubmit={onSubmitHandler} onCancel={onCancelHandler} />
        </Container>
    );
};
