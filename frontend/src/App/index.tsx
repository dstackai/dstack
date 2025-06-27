import React, { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, useLocation } from 'react-router-dom';

import AppLayout from 'layouts/AppLayout';

import { useAppDispatch, useAppSelector } from 'hooks';
import { useGetUserDataQuery } from 'services/user';

import { EnterpriseLogin } from './Login/EnterpriseLogin';
import { LoginByGithub } from './Login/LoginByGithub';
import { ROUTES } from '../routes';
import { AuthErrorMessage } from './AuthErrorMessage';
import { selectAuthToken, setUserData } from './slice';

const localStorageIsAvailable = 'localStorage' in window;

const IGNORED_AUTH_PATHS = [
    ROUTES.AUTH.GITHUB_CALLBACK,
    ROUTES.AUTH.OKTA_CALLBACK,
    ROUTES.AUTH.ENTRA_CALLBACK,
    ROUTES.AUTH.GOOGLE_CALLBACK,
    ROUTES.AUTH.TOKEN,
];

const LoginFormComponent = process.env.UI_VERSION === 'enterprise' ? EnterpriseLogin : LoginByGithub;

const App: React.FC = () => {
    const { t } = useTranslation();
    const token = useAppSelector(selectAuthToken);
    const isAuthenticated = Boolean(token);
    const dispatch = useAppDispatch();
    const { pathname } = useLocation();

    const {
        isLoading,
        data: userData,
        error: getUserError,
    } = useGetUserDataQuery(
        { token },
        {
            skip: !isAuthenticated || !localStorageIsAvailable,
        },
    );

    useEffect(() => {
        if (userData?.username || getUserError) {
            if (userData?.username) {
                dispatch(setUserData(userData));
            }
        }
    }, [userData, getUserError, isLoading]);

    const renderLocalstorageError = () => {
        return (
            <AuthErrorMessage
                title={t('common.local_storage_unavailable')}
                text={t('common.local_storage_unavailable_message')}
            />
        );
    };

    const renderTokenError = () => {
        return <LoginFormComponent />;
    };

    const renderNotAuthorizedError = () => {
        return <LoginFormComponent />;
    };

    if (IGNORED_AUTH_PATHS.includes(pathname)) {
        return <Outlet />;
    }

    if (!localStorageIsAvailable) return renderLocalstorageError();
    if (getUserError) return renderTokenError();
    if (!isAuthenticated) return renderNotAuthorizedError();

    return (
        <AppLayout>
            <Outlet />
        </AppLayout>
    );
};

export default App;
