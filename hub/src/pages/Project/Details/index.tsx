import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, useLocation, useNavigate, useParams } from 'react-router-dom';
import Box from '@cloudscape-design/components/box';

import { Button, ButtonProps, ConfirmationDialog, ContentLayout, DetailsHeader } from 'components';

import { useAppSelector, useNotifications } from 'hooks';
import { ROUTES } from 'routes';
import { useDeleteProjectsMutation, useGetProjectQuery } from 'services/project';

import { selectUserData } from 'App/slice';

import { getProjectRoleByUserName } from '../utils';

export const ProjectDetails: React.FC = () => {
    const { t } = useTranslation();
    const [showDeleteConfirm, setShowConfirmDelete] = useState(false);
    const { pathname } = useLocation();
    const params = useParams();
    const userData = useAppSelector(selectUserData);
    const userName = userData?.user_name ?? '';
    const userGlobalRole = userData?.global_role ?? '';
    const paramProjectName = params.name ?? '';
    const navigate = useNavigate();
    const { data } = useGetProjectQuery({ name: paramProjectName });
    const [deleteProjects, { isLoading: isDeleting }] = useDeleteProjectsMutation();
    const [pushNotification] = useNotifications();

    const isDisabledButtons = useMemo<boolean>(() => {
        return isDeleting || !data || (getProjectRoleByUserName(data, userName) !== 'admin' && userGlobalRole !== 'admin');
    }, [data, userName, userGlobalRole]);

    const toggleDeleteConfirm = () => {
        setShowConfirmDelete((val) => !val);
    };

    const deleteUserHandler = () => {
        if (!data) return;

        deleteProjects([paramProjectName])
            .unwrap()
            .then(() => navigate(ROUTES.PROJECT.LIST))
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: error?.error }),
                });
            });

        setShowConfirmDelete(false);
    };

    const goToProjectSettings: ButtonProps['onClick'] = (event) => {
        event.preventDefault();

        navigate(ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName));
    };

    const addBackendHandler = () => {
        navigate(ROUTES.PROJECT.BACKEND.ADD.FORMAT(paramProjectName));
    };

    const isSettingsPage = pathname === ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName);

    return (
        <>
            <ContentLayout
                header={
                    <DetailsHeader
                        title={paramProjectName}
                        deleteAction={isSettingsPage ? toggleDeleteConfirm : undefined}
                        deleteDisabled={isDisabledButtons}
                        actionButtons={
                            <>
                                {isSettingsPage && (
                                    <Button onClick={addBackendHandler} disabled={isDisabledButtons}>
                                        {t('backend.add_backend')}
                                    </Button>
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

            <ConfirmationDialog
                visible={showDeleteConfirm}
                onDiscard={toggleDeleteConfirm}
                onConfirm={deleteUserHandler}
                title={t('projects.edit.delete_project_confirm_title')}
                content={<Box variant="span">{t('projects.edit.delete_project_confirm_message')}</Box>}
            />
        </>
    );
};
