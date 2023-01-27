import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams, Routes, Route, Navigate } from 'react-router-dom';
import { useGetUserDataQuery } from 'services/user';
import { isValidToken } from 'libs';
import { useAppDispatch, useAppSelector } from 'hooks';
import AppLayout from 'layouts/AppLayout';
import { Box } from 'components';
import { ROUTES } from 'routes';
import { removeAuthData, selectAuthToken, setAuthData, setUserData } from './slice';
import { AuthErrorMessage } from './AuthErrorMessage';
import { Loading } from './Loading';
import { Logout } from './Logout';
import { Hub } from 'pages/Hub';

const App: React.FC = () => {
    const { t } = useTranslation();
    const [searchParams, setSearchParams] = useSearchParams();
    const urlToken = searchParams.get('token');
    const storeToken = useAppSelector(selectAuthToken);
    const isAuthenticated = useAppSelector(selectAuthToken);
    const [isAuthorizing, setIsAuthorizing] = useState(isValidToken(urlToken || storeToken));
    const dispatch = useAppDispatch();

    const {
        isLoading,
        data: userData,
        error: getUserError,
    } = useGetUserDataQuery(
        {
            token: (urlToken || storeToken) as string,
        },
        {
            skip: !isAuthenticated && !urlToken,
        },
    );

    useEffect(() => {
        if (userData?.user_name || getUserError) {
            setIsAuthorizing(false);

            if (userData?.user_name) {
                if (urlToken) {
                    dispatch(setAuthData({ token: urlToken as string }));
                }
                dispatch(setUserData(userData));
            } else if (getUserError) {
                dispatch(removeAuthData());
            }

            if (urlToken) {
                setSearchParams();
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
            <Routes>
                <Route path={ROUTES.BASE} element={<Navigate replace to={ROUTES.HUB.LIST} />} />
                <Route path={ROUTES.HUB.LIST} element={<Hub />} />
                <Route path={ROUTES.USER.LIST} element={<Box variant="h1">User list</Box>} />
                <Route path={ROUTES.LOGOUT} element={<Logout />} />
            </Routes>
        </AppLayout>
    );
};

export default App;
