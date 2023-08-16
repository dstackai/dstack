import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, useLocation, useNavigate, useParams } from 'react-router-dom';

import { Button, ButtonProps, ButtonWithConfirmation, ContentLayout, DetailsHeader } from 'components';

import { ROUTES } from 'routes';
import { useGetProjectQuery } from 'services/project';

import { useCheckAvailableProjectPermission } from '../hooks/useCheckAvailableProjectPermission';
import { useDeleteProject } from '../hooks/useDeleteProject';

export const ProjectDetails: React.FC = () => {
    const { t } = useTranslation();
    const { pathname } = useLocation();
    const params = useParams();
    const paramProjectName = params.name ?? '';
    const navigate = useNavigate();
    const { data } = useGetProjectQuery({ name: paramProjectName });
    const { deleteProject, isDeleting } = useDeleteProject();

    const { isAvailableDeletingPermission } = useCheckAvailableProjectPermission();

    const isDisabledButtons = useMemo<boolean>(() => {
        return isDeleting || !data || !isAvailableDeletingPermission(data);
    }, [data, isDeleting]);

    const deleteProjectHandler = () => {
        if (!data) return;

        deleteProject(data).then(() => navigate(ROUTES.PROJECT.LIST));
    };

    const goToProjectSettings: ButtonProps['onClick'] = (event) => {
        event.preventDefault();

        navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName));
    };

    const isSettingsPage = pathname === ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName);

    return (
        <>
            <ContentLayout
                header={
                    <DetailsHeader
                        title={paramProjectName}
                        actionButtons={
                            <>
                                {isSettingsPage && (
                                    <ButtonWithConfirmation
                                        disabled={isDisabledButtons}
                                        formAction="none"
                                        onClick={deleteProjectHandler}
                                        confirmTitle={t('projects.edit.delete_project_confirm_title')}
                                        confirmContent={t('projects.edit.delete_project_confirm_message')}
                                    >
                                        {t('common.delete')}
                                    </ButtonWithConfirmation>
                                )}

                                {!isSettingsPage ? (
                                    <Button
                                        href={ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName)}
                                        onClick={goToProjectSettings}
                                    >
                                        {t('common.settings')}
                                    </Button>
                                ) : null}
                            </>
                        }
                    />
                }
            >
                <Outlet />
            </ContentLayout>
        </>
    );
};
