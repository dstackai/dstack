import React, { useEffect, useState } from 'react';
import { useSearchParams, Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useGetUserDataQuery } from 'services/user';
import { useAppDispatch, useAppSelector } from 'hooks';
import { selectAuthToken, setAuthData, setUserData } from './slice';
import { AuthErrorMessage } from './AuthErrorMessage';
import AppLayout from 'layouts/AppLayout';
import { Loading } from './Loading';

const App: React.FC = () => {
    const { t } = useTranslation();
    const [searchParams, setSearchParams] = useSearchParams();
    const urlToken = searchParams.get('token');
    const isAuthenticated = Boolean(useAppSelector(selectAuthToken));
    const [isAuthorizing, setIsAuthorizing] = useState(true);
    const dispatch = useAppDispatch();

    const {
        isLoading,
        data: userData,
        error: getUserError,
    } = useGetUserDataQuery(undefined, {
        skip: !isAuthenticated || !!urlToken,
    });

    useEffect(() => {
        if (!isAuthenticated && !urlToken) {
            setIsAuthorizing(false);
        }

        if (urlToken) {
            dispatch(setAuthData({ token: urlToken as string }));
            setSearchParams();
        }
    }, []);

    useEffect(() => {
        if (userData?.user_name || getUserError) {
            setIsAuthorizing(false);

            if (userData?.user_name) {
                dispatch(setUserData(userData));
            }
        }
    }, [userData, getUserError, isLoading]);

    const renderTokenError = () => {
        return <AuthErrorMessage title={t('auth.invalid_token')} text={t('auth.contact_to_administrator')} />;
    };

    const renderNotAuthorizedError = () => {
        return <AuthErrorMessage title={t('auth.you_are_not_logged_in')} text={t('auth.contact_to_administrator')} />;
    };

    if (isAuthorizing) return <Loading />;

    if (getUserError) return renderTokenError();

    if (!isAuthenticated && !urlToken) return renderNotAuthorizedError();

    return (
        <AppLayout>
            <Outlet />
        </AppLayout>
    );
};

export default App;
