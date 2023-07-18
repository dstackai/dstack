import React from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import { Container, ContentLayout, Header, Loader } from 'components';

import { useBreadcrumbs, useNotifications } from 'hooks';
import { ROUTES } from 'routes';
import { useGetProjectWithConfigInfoQuery, useUpdateProjectMutation } from 'services/project';

import { ProjectForm } from '../Form';

export const ProjectEditBackend: React.FC = () => {
    const { t } = useTranslation();
    const params = useParams();
    const paramProjectName = params.name ?? '';
    const navigate = useNavigate();
    const [pushNotification] = useNotifications();
    const { data, isLoading } = useGetProjectWithConfigInfoQuery({ name: paramProjectName });
    const [updateProject, { isLoading: isProjectUpdating }] = useUpdateProjectMutation();

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
            text: t('projects.edit.edit_backend'),
            href: ROUTES.USER.EDIT.FORMAT(paramProjectName),
        },
    ]);

    const onCancelHandler = () => {
        navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName));
    };

    const onSubmitHandler = async (data: Partial<IProject>): Promise<IProject> => {
        const request = updateProject({
            ...data,
            project_name: paramProjectName,
        }).unwrap();

        try {
            const data = await request;

            pushNotification({
                type: 'success',
                content: t('projects.edit.success_notification'),
            });

            navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(data.project_name ?? paramProjectName));
        } catch (e) {
            console.log(e);
        }

        return request;
    };

    return (
        <ContentLayout header={<Header variant="awsui-h1-sticky">{paramProjectName}</Header>}>
            {isLoading && !data && (
                <Container>
                    <Loader />
                </Container>
            )}

            {data && (
                <ProjectForm
                    initialValues={data}
                    loading={isProjectUpdating}
                    onSubmit={onSubmitHandler}
                    onCancel={onCancelHandler}
                />
            )}
        </ContentLayout>
    );
};
