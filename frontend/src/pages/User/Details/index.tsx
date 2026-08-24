import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, useNavigate, useParams } from 'react-router-dom';

import { Box, ConfirmationDialog, ContentLayout, Tabs } from 'components';
import { DetailsHeader } from 'components';

import { useNotifications /* usePermissionGuard*/ } from 'hooks';
import { getServerError, riseRouterException } from 'libs';
import { ROUTES } from 'routes';
import { useDeleteUsersMutation, useGetUserQuery } from 'services/user';

// import { GlobalUserRole } from '../../../types';
import { UserDetailsTabTypeEnum } from './types';

import styles from './styles.module.scss';

export { Settings as UserSettings } from './Settings';
export { Billing as UserBilling } from './Billing';
export { Events as UserEvents } from './Events';
export { UserProjectList as UserProjects } from './Projects';

export const UserDetails: React.FC = () => {
    const { t } = useTranslation();
    const [showDeleteConfirm, setShowConfirmDelete] = useState(false);
    const params = useParams();
    const paramUserName = params.userName ?? '';
    const navigate = useNavigate();
    const { error: userError } = useGetUserQuery({ name: paramUserName });
    const [deleteUsers /*, { isLoading: isDeleting }*/] = useDeleteUsersMutation();
    const [pushNotification] = useNotifications();
    // const [isAvailableDeleteUser] = usePermissionGuard({ allowedGlobalRoles: [GlobalUserRole.ADMIN] });

    useEffect(() => {
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-ignore
        if (userError?.status === 404) {
            riseRouterException();
        }
    }, [userError]);

    const toggleDeleteConfirm = () => {
        setShowConfirmDelete((val) => !val);
    };

    const deleteUserHandler = () => {
        deleteUsers([paramUserName])
            .unwrap()
            .then(() => navigate(ROUTES.USER.LIST))
            .catch((error) => {
                pushNotification({
                    type: 'error',
                    content: t('common.server_error', { error: getServerError(error) }),
                });
            });

        setShowConfirmDelete(false);
    };

    const tabs: {
        label: string;
        id: UserDetailsTabTypeEnum;
        href: string;
    }[] = [
        {
            label: t('users.settings'),
            id: UserDetailsTabTypeEnum.SETTINGS,
            href: ROUTES.USER.DETAILS.FORMAT(paramUserName),
        },
        {
            label: t('users.projects'),
            id: UserDetailsTabTypeEnum.PROJECTS,
            href: ROUTES.USER.PROJECTS.FORMAT(paramUserName),
        },
        {
            label: t('users.events'),
            id: UserDetailsTabTypeEnum.EVENTS,
            href: ROUTES.USER.EVENTS.FORMAT(paramUserName),
        },
        process.env.UI_VERSION === 'sky' && {
            label: t('billing.title'),
            id: UserDetailsTabTypeEnum.BILLING,
            href: ROUTES.USER.BILLING.LIST.FORMAT(paramUserName),
        },
    ].filter(Boolean);

    return (
        <div className={styles.page}>
            <ContentLayout
                header={
                    <DetailsHeader
                        title={paramUserName}
                        // deleteAction={isAvailableDeleteUser ? toggleDeleteConfirm : undefined}
                        // deleteDisabled={isDeleting}
                    />
                }
            >
                <Tabs withNavigation tabs={tabs} />

                <Outlet />
            </ContentLayout>

            <ConfirmationDialog
                visible={showDeleteConfirm}
                content={<Box variant="span">{t('confirm_dialog.message')}</Box>}
                onDiscard={toggleDeleteConfirm}
                onConfirm={deleteUserHandler}
                confirmButtonLabel={t('common.delete')}
            />
        </div>
    );
};
