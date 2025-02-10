import React from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { ContentLayout, Header } from 'components';

import { useBreadcrumbs, useNotifications } from 'hooks';
import { getServerError } from 'libs';
import { ROUTES } from 'routes';
import { useCreateProjectMutation } from 'services/project';

import { ProjectForm } from '../Form';

export const ProjectAdd: React.FC = () => {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();
    const [createProject, { isLoading }] = useCreateProjectMutation();

    useBreadcrumbs([
        {
            text: t('navigation.project_other'),
            href: ROUTES.PROJECT.LIST,
        },
        {
            text: t('common.create', { text: t('navigation.project') }),
            href: ROUTES.PROJECT.ADD,
        },
    ]);

    const onCancelHandler = () => {
        navigate(ROUTES.PROJECT.LIST);
    };

    const onSubmitHandler = async (data: IProject): Promise<IProject> => {
        const request = createProject(data).unwrap();

        request
            .then((data) => {
                pushNotification({
                    type: 'success',
                    content: t('projects.create.success_notification'),
                });

                navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(data.project_name));
            })
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: getServerError(error) }),
                });
            });

        return request;
    };

    return (
        <ContentLayout header={<Header variant="awsui-h1-sticky">{t('projects.create.page_title')}</Header>}>
            <ProjectForm onSubmit={onSubmitHandler} loading={isLoading} onCancel={onCancelHandler} />
        </ContentLayout>
    );
};
