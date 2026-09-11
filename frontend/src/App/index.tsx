import React, { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, Outlet, useLocation } from 'react-router-dom';

import AppLayout from 'layouts/AppLayout';

import { useAppDispatch, useAppSelector } from 'hooks';
import { useGetUserDataQuery } from 'services/user';

import { SelfHostedLogin } from './Login/SelfHostedLogin';
import { ROUTES } from '../routes';
import { AuthErrorMessage } from './AuthErrorMessage';
import { Loading } from './Loading';
import { selectAuthToken, setUserData } from './slice';

const IGNORED_AUTH_PATHS = [
    ROUTES.AUTH.GITHUB_CALLBACK,
    ROUTES.AUTH.OKTA_CALLBACK,
    ROUTES.AUTH.ENTRA_CALLBACK,
    ROUTES.AUTH.GOOGLE_CALLBACK,
    ROUTES.AUTH.TOKEN,
];

const LoginFormComponent =
    process.env.UI_VERSION === 'sky' ? () => <Navigate replace to={ROUTES.AUTH.LOGIN} /> : SelfHostedLogin;

const App: React.FC = () => {
    const { t } = useTranslation();
    const token = useAppSelector(selectAuthToken);
    const localStorageIsAvailable = 'localStorage' in window;
    const dispatch = useAppDispatch();
    const { pathname } = useLocation();

    const {
        isFetching,
        currentData: userData,
        error: getUserError,
    } = useGetUserDataQuery(
        { token },
        {
            skip: !token || !localStorageIsAvailable,
        },
    );

    useEffect(() => {
        if (userData?.username && !getUserError) {
            dispatch(setUserData(userData));
        }
    }, [userData, getUserError, dispatch]);

    if (IGNORED_AUTH_PATHS.includes(pathname)) {
        return <Outlet />;
    }

    if (!localStorageIsAvailable) {
        return (
            <AuthErrorMessage
                title={t('common.local_storage_unavailable')}
                text={t('common.local_storage_unavailable_message')}
            />
        );
    }
    if (!token || getUserError) return <LoginFormComponent />;
    if (isFetching && !userData) return <Loading />;
    if (!userData?.username) return <LoginFormComponent />;

    return (
        <AppLayout>
            <Outlet />
        </AppLayout>
    );
};

export default App;
