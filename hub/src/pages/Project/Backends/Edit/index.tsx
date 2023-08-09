import React from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import { Container, Header, Loader } from 'components';

import { useBreadcrumbs, useNotifications } from 'hooks';
import { ROUTES } from 'routes';
import { useGetBackendConfigQuery, useUpdateBackendMutation } from 'services/backend';

import { BackendForm } from '../Form';

export const BackendEdit: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.name ?? '';
    const paramBackendName = params.backend ?? '';
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();
    const [updateProject, { isLoading: isBackendUpdating }] = useUpdateBackendMutation();

    const { data, isLoading } = useGetBackendConfigQuery({ projectName: paramProjectName, backendName: paramBackendName });

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
            text: t('backend.edit_backend'),
            href: ROUTES.PROJECT.BACKEND.ADD.FORMAT(paramProjectName),
        },
    ]);

    const onCancelHandler = () => {
        navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName));
    };

    const onSubmitHandler = async (data: TBackendConfig): Promise<TBackendConfig> => {
        const request = updateProject({
            projectName: paramProjectName,
            config: data,
        }).unwrap();

        request
            .then(() => {
                pushNotification({
                    type: 'success',
                    content: t('backend.edit.success_notification'),
                });

                navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName));
            })
            .catch((error) => console.log(error));

        return request;
    };

    if (isLoading && !data)
        return (
            <Container>
                <Loader />
            </Container>
        );

    return (
        <Container header={<Header variant="h2">{t('backend.edit_backend')}</Header>}>
            {data && (
                <BackendForm
                    initialValues={data.config}
                    loading={isBackendUpdating}
                    onSubmit={onSubmitHandler}
                    onCancel={onCancelHandler}
                />
            )}
        </Container>
    );
};
