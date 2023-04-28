import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, useLocation, useNavigate, useParams } from 'react-router-dom';

import { ConfirmationDialog, ContentLayout, DetailsHeader, SpaceBetween, Tabs, TabsProps } from 'components';

import { useAppSelector, useNotifications } from 'hooks';
import { ROUTES } from 'routes';
import { useDeleteProjectsMutation, useGetProjectQuery } from 'services/project';

import { selectUserData } from 'App/slice';

import { getProjectRoleByUserName } from '../utils';

import styles from './styles.module.scss';

enum TabTypesEnum {
    REPOSITORIES = 'repositories',
    SETTINGS = 'settings',
}

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

    const tabs: {
        label: string;
        id: TabTypesEnum;
        href: string;
    }[] = [
        {
            label: t('projects.repositories'),
            id: TabTypesEnum.REPOSITORIES,
            href: ROUTES.PROJECT.DETAILS.REPOSITORIES.FORMAT(paramProjectName),
        },
        {
            label: t('projects.settings'),
            id: TabTypesEnum.SETTINGS,
            href: ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName),
        },
    ];

    const onChangeTab: TabsProps['onChange'] = ({ detail }) => {
        // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
        navigate(detail.activeTabHref!);
    };

    const activeTabId = useMemo(() => {
        const tab = tabs.find((t) => pathname === t.href);

        return tab?.id;
    }, [pathname]);

    const isVisibleTabs = useMemo(() => {
        return [
            ROUTES.PROJECT.DETAILS.REPOSITORIES.FORMAT(paramProjectName),
            ROUTES.PROJECT.DETAILS.SETTINGS.FORMAT(paramProjectName),
        ].includes(pathname);
    }, [pathname]);

    return (
        <>
            <ContentLayout
                header={
                    <DetailsHeader
                        title={paramProjectName}
                        deleteAction={toggleDeleteConfirm}
                        deleteDisabled={isDisabledButtons}
                    />
                }
            >
                <SpaceBetween size="l">
                    {isVisibleTabs && (
                        <div className={styles.tabs}>
                            <Tabs onChange={onChangeTab} activeTabId={activeTabId} tabs={tabs} />
                        </div>
                    )}

                    <Outlet />
                </SpaceBetween>
            </ContentLayout>

            <ConfirmationDialog visible={showDeleteConfirm} onDiscard={toggleDeleteConfirm} onConfirm={deleteUserHandler} />
        </>
    );
};
