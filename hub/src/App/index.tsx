import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams, Routes, Route, Navigate } from 'react-router-dom';
import { useCheckTokenMutation } from 'services/auth';
import { isValidToken } from 'libs';
import { useAppDispatch, useAppSelector } from 'hooks';
import AppLayout from 'layouts/AppLayout';
import { Box } from 'components';
import { ROUTES } from 'routes';
import { selectIsAuthenticated, setAuthData } from './slice';
import { AuthErrorMessage } from './AuthErrorMessage';
import { Loading } from './Loading';
import { Logout } from './Logout';
import { Hub } from 'pages/Hub';

const App: React.FC = () => {
    const { t } = useTranslation();
    const [searchParams, setSearchParams] = useSearchParams();
    const token = searchParams.get('token');
    const isAuthenticated = useAppSelector(selectIsAuthenticated);
    const [isAuthorizing, setIsAuthorizing] = useState(isValidToken(token));
    const dispatch = useAppDispatch();

    const [checkToken, { isLoading, data: checkingData, error: checkingError }] = useCheckTokenMutation();

    useEffect(() => {
        if (isValidToken(token)) {
            checkToken({ token: token ?? '' });
            setSearchParams();
        }
    }, []);

    useEffect(() => {
        if (checkingData?.token || checkingError) {
            setIsAuthorizing(false);

            if (checkingData?.token) dispatch(setAuthData(checkingData));
        }
    }, [checkingData, checkingError, isLoading]);

    const renderTokenError = () => {
        const errorData = checkingError && 'data' in checkingError ? (checkingError.data as { error_code: string }) : null;
        if (errorData)
            return <AuthErrorMessage title={t(`auth.${errorData.error_code}`)} text={t('auth.contact_to_administrator')} />;
        return <AuthErrorMessage title={t('auth.token_error')} text={t('auth.contact_to_administrator')} />;
    };

    const renderNotAuthorizedError = () => {
        return <AuthErrorMessage title={t('auth.you_are_not_logged_in')} text={t('auth.contact_to_administrator')} />;
    };

    if (isAuthorizing) return <Loading />;

    if (checkingError) return renderTokenError();

    if (!isAuthenticated && !token) return renderNotAuthorizedError();

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
