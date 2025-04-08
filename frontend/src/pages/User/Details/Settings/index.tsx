import React from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import { Box, Button, ColumnLayout, Container, Header, Loader, Popover, SpaceBetween, StatusIndicator } from 'components';
import { PermissionGuard } from 'components/PermissionGuard';

import { useAppSelector, useBreadcrumbs, usePermissionGuard } from 'hooks';
import { copyToClipboard } from 'libs';
import { ROUTES } from 'routes';
import { useDeleteUsersMutation, useGetUserQuery } from 'services/user';
import { GlobalUserRole } from 'types';

import { selectUserData } from 'App/slice';

import styles from './styles.module.scss';

export const Settings: React.FC = () => {
    const { t } = useTranslation();
    const userData = useAppSelector(selectUserData);
    const params = useParams();
    const paramUserName = params.userName ?? '';
    const navigate = useNavigate();

    const { isLoading, data } = useGetUserQuery({ name: paramUserName }, { skip: !params.userName });
    const [, { isLoading: isDeleting }] = useDeleteUsersMutation();

    const [isAvailableDelete] = usePermissionGuard({ allowedGlobalRoles: [GlobalUserRole.ADMIN] });

    useBreadcrumbs([
        {
            text: t('navigation.account'),
            href: ROUTES.USER.LIST,
        },
        {
            text: paramUserName,
            href: ROUTES.USER.DETAILS.FORMAT(paramUserName),
        },
    ]);

    const editUserHandler = () => {
        navigate(ROUTES.USER.EDIT.FORMAT(paramUserName));
    };

    const isDisabledUserEditing = () => {
        return isDeleting || (!isAvailableDelete && userData?.username !== paramUserName);
    };

    const onCopyToken = () => {
        copyToClipboard(data?.creds.token ?? '');
    };

    return (
        <div>
            <Container
                header={
                    <Header
                        variant="h2"
                        actions={
                            <Button onClick={editUserHandler} disabled={isDisabledUserEditing()}>
                                {t('common.edit')}
                            </Button>
                        }
                    >
                        {t('users.account_settings')}
                    </Header>
                }
            >
                {isLoading && <Loader />}

                {data && (
                    <ColumnLayout columns={2} variant="text-grid">
                        <SpaceBetween size="l">
                            {/*<div>*/}
                            {/*    <Box variant="awsui-key-label">{t('users.user_name')}</Box>*/}
                            {/*    <div>{data.user_name}</div>*/}
                            {/*</div>*/}

                            <div>
                                <Box variant="awsui-key-label">{t('users.email')}</Box>
                                <div>{data.email ?? '-'}</div>
                            </div>

                            <PermissionGuard allowedGlobalRoles={[GlobalUserRole.ADMIN]}>
                                <div>
                                    <Box variant="awsui-key-label">{t('users.global_role')}</Box>
                                    <div>{t(`roles.${data.global_role}`)}</div>
                                </div>
                            </PermissionGuard>

                            <div>
                                <Box variant="awsui-key-label">{t('users.token')}</Box>

                                <div className={styles.token}>
                                    <Popover
                                        dismissButton={false}
                                        position="top"
                                        size="small"
                                        triggerType="custom"
                                        content={<StatusIndicator type="success">{t('users.token_copied')}</StatusIndicator>}
                                    >
                                        <Button formAction="none" iconName="copy" variant="link" onClick={onCopyToken} />
                                    </Popover>

                                    <div>{data.creds.token}</div>
                                </div>
                            </div>
                        </SpaceBetween>
                    </ColumnLayout>
                )}
            </Container>
        </div>
    );
};
